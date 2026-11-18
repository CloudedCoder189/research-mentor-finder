"""Synthetic documents and isolated accounts only; never uses owner files or AI."""
import base64
import io
import subprocess
import threading
import zipfile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import database
from api.main import create_app
from api.resume_parser import extract, suggestions, MAX_BYTES
from tests._auth_helpers import client_for_user

TEXT = 'Example Student\nSkills\nPython, SQL; Python\nCoursework\nAlgorithms\nExperience\nBuilt a sensor project\nEducation\nExample School'


def docx(xml):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', xml)
    return out.getvalue()


def pdf(pages=1, encrypted=False, text=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        if text:
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(b'BT /F1 12 Tf 50 700 Td (Skills) Tj 0 -20 Td (Python) Tj ET')
            page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('synthetic-password')
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_text_normalization_and_suggestions():
    text = extract('txt', b'\xef\xbb\xbf' + TEXT.replace('\n', '\r\n').encode())
    assert text == TEXT
    assert suggestions(text) == {'skills': ['Python', 'SQL'], 'coursework': ['Algorithms'], 'experience': ['Built a sensor project']}


def test_docx_and_pdf_extract_real_text():
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Skills</w:t></w:r></w:p><w:p><w:r><w:t>Python</w:t></w:r></w:p></w:body></w:document>'
    assert extract('docx', docx(xml.encode())) == 'Skills\nPython'
    assert suggestions(extract('pdf', pdf(text=True)))['skills'] == ['Python']


@pytest.mark.parametrize('kind,data', [('txt', b''), ('txt', b'x' * (MAX_BYTES + 1)), ('txt', b'x' * 20001), ('txt', b'\x00'), ('txt', b'\xff'), ('doc', b'example'), ('docx', b'not a zip'), ('pdf', b'not a pdf'), ('pdf', b'%PDF-broken'), ('pdf', pdf()), ('pdf', pdf(11)), ('pdf', pdf(encrypted=True)), ('docx', docx(b'<!DOCTYPE x [<!ENTITY a "secret">]><x/>')), ('docx', docx(b'x' * (2*1024*1024+1)))], ids=['empty','bytes-limit','text-limit','nul','encoding','old-doc','bad-docx','bad-pdf','broken-pdf','scanned','pages','password','entities','xml-limit'])
def test_rejects_bad_or_unbounded_documents(kind, data):
    with pytest.raises(Exception):
        extract(kind, data)


def test_suggestions_bounded_and_contact_lines_excluded():
    result = suggestions('Skills\n' + '\n'.join('item' + str(n) for n in range(40)) + '\nprivate@example.invalid\nhttps://example.invalid\nExperience\n' + 'x'*300)
    assert len(result['skills']) == 30
    assert len(result['experience'][0]) == 250
    assert all('@' not in item and 'http' not in item for item in result['skills'])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'disposable.db')
    monkeypatch.setenv('APP_MODE', 'local')
    monkeypatch.delenv('RATE_LIMIT_LOCAL', raising=False)
    database.initialize_database()
    return client_for_user('resume-test', 'resume-test@example.invalid')


def payload(data=TEXT.encode(), kind='txt', user='resume-test'):
    return {'expected_user_id': user, 'kind': kind, 'content': base64.b64encode(data).decode()}


def test_preview_uses_worker_and_does_not_save_profile(client, tmp_path):
    before = client.get('/api/profile').json()
    files_before = {p.relative_to(tmp_path) for p in tmp_path.rglob('*')}
    response = client.post('/api/profile/resume-preview', json=payload())
    assert response.status_code == 200
    assert response.json()['skills'] == ['Python', 'SQL']
    assert client.get('/api/profile').json() == before
    new_files = {p.relative_to(tmp_path) for p in tmp_path.rglob('*')} - files_before
    assert all(p.parts[0] == '.account_locks' for p in new_files)


def test_auth_csrf_and_stale_account(client):
    assert TestClient(create_app()).post('/api/profile/resume-preview', json=payload()).status_code == 401
    assert client.post('/api/profile/resume-preview', json=payload(user='other')).status_code == 409
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/profile/resume-preview', json=payload()).status_code == 403


@pytest.mark.parametrize('body', [payload(kind='doc'), payload(data=b''), payload(data=b'x'*(MAX_BYTES+1)), {**payload(), 'content': 'not base64'}, {**payload(), 'surprise': True}])
def test_invalid_requests(client, body):
    assert client.post('/api/profile/resume-preview', json=body).status_code == 422


def test_busy_timeout_and_release(client, monkeypatch):
    from api.routes import resume
    monkeypatch.setattr(resume, 'slots', threading.BoundedSemaphore(1))
    resume.slots.acquire()
    assert client.post('/api/profile/resume-preview', json=payload()).status_code == 503
    resume.slots.release()
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('worker', 8)
    monkeypatch.setattr(resume.subprocess, 'run', timeout)
    assert client.post('/api/profile/resume-preview', json=payload()).status_code == 422
    assert resume.slots.acquire(blocking=False)
    resume.slots.release()


def test_broken_worker_response_is_safe(client, monkeypatch):
    from api.routes import resume
    monkeypatch.setattr(resume.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 0, stdout='not-json', stderr='private diagnostic'))
    response = client.post('/api/profile/resume-preview', json=payload())
    assert response.status_code == 503
    assert 'private' not in response.text


def test_worker_library_error_does_not_disclose_diagnostics(client):
    response = client.post('/api/profile/resume-preview', json=payload(b'not a zip', 'docx'))
    assert response.status_code == 422
    assert response.json()['detail'] == 'This file could not be read. Export a text résumé instead.'


def test_fragmented_document_pdf_keeps_courses_and_sentences():
    from pypdf import PdfReader
    from api.resume_smoke import fragmented_pdf, COURSES, EXPERIENCES
    data = fragmented_pdf()
    # Prove the fixture exercises the old plain-extraction failure.
    plain = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert suggestions(plain)['coursework'] != COURSES
    actual = suggestions(extract('pdf', data))
    assert actual['coursework'] == COURSES
    assert actual['experience'] == EXPERIENCES
    assert actual['skills'] == ['Python', 'SQL']


def test_experience_continuations_keep_explicit_bullets_separate():
    actual = suggestions('Experience\nBuilt a sensor and recorded\nmeasurements using Python.\n• developed a chart\n• tested the sensor')
    assert actual['experience'] == ['Built a sensor and recorded measurements using Python.', 'developed a chart', 'tested the sensor']
