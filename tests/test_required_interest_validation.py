import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.services import StudentProfileInput

@pytest.mark.parametrize('interests',[[''],['   '],['\t\n'],['\u00a0','\u2003']])
def test_blank_required_interests_rejected_on_both_endpoints(interests):
    client=TestClient(create_app())
    for route,extra in (('/api/recommendations',{}),('/api/recommendations/explain',{'researcher_id':1})):
        response=client.post(route,json={'profile':{'interests':interests},**extra})
        assert response.status_code==422
        assert any(error['loc']==['body','profile','interests'] for error in response.json()['detail'])

def test_valid_interests_trimmed_without_reordering():
    profile=StudentProfileInput(interests=['  robotics ','\t',' biology\n'])
    assert profile.interests==['robotics','biology']
