"""Container build check using synthetic documents; no database or provider access."""
import base64
import io
import json
import subprocess
import sys
import zipfile
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


COURSES = ["Introduction to Computer Science", "Statistics", "Calculus", "Physics", "Environmental Science"]
EXPERIENCES = [
    "Built an Arduino temperature sensor and recorded measurements using Python.",
    "Created charts comparing temperature readings across different indoor locations.",
    "Trained a simple image classifier using a small public practice dataset.",
    "Documented project methods, results, and limitations in a short research report.",
]


def fragmented_pdf():
    """Words individually translated, as in some document-export PDFs."""
    import textwrap
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Courier')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    rows = ['SKILLS', 'Python', 'SQL', 'COURSEWORK', *COURSES, 'EXPERIENCE']
    for sentence in EXPERIENCES:
        rows.extend(textwrap.wrap(sentence, width=68))
    rows += ['INTERESTS', 'Robotics']
    operations = []
    for row, line in enumerate(rows):
        x = 50.0
        for word in line.split():
            operations.append(f'q 1 0 0 1 {x:.2f} {740-row*20} cm BT /F1 12 Tf ({word}) Tj ET Q')
            x += (len(word) + 1) * 7.2
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(operations).encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main():
    xml = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Skills</w:t></w:r></w:p><w:p><w:r><w:t>Python</w:t></w:r></w:p></w:body></w:document>'
    doc = io.BytesIO()
    with zipfile.ZipFile(doc, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 50 700 Td (Skills) Tj 0 -20 Td (Python) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    pdf = io.BytesIO()
    writer.write(pdf)
    fragmented = fragmented_pdf()
    for kind, data in [('txt', b'Skills\nPython'), ('docx', doc.getvalue()), ('pdf', pdf.getvalue()), ('pdf', fragmented)]:
        run = subprocess.run([sys.executable, '-m', 'api.resume_worker'], input=json.dumps({'kind':kind,'content':base64.b64encode(data).decode()}), text=True, capture_output=True, timeout=8, check=True)
        result = json.loads(run.stdout)
        assert result['skills'][0] == 'Python', 'Synthetic parsing check failed'
        if data is fragmented:
            assert result['coursework'] == COURSES
            assert result['experience'] == EXPERIENCES
    print('Synthetic resume worker checks passed: TXT, DOCX, PDF.')


if __name__ == '__main__':
    main()
