import pytest

from api.schemas.researcher import summary_dto
from services.ui_helpers import field_filter_matches


JOINT = {"id": 129, "department": "Electrical and Computer Engineering; Computer Science",
         "field": "Not publicly available", "discipline": "Not publicly available"}


@pytest.mark.parametrize("selected", ["Computing", "Engineering", "Computer Science", "Electrical and Computer Engineering"])
def test_joint_appointments_match_each_documented_field(selected):
    assert field_filter_matches(JOINT, selected)


def test_joint_appointments_do_not_match_unrelated_fields():
    assert not field_filter_matches(JOINT, "Bioengineering")


def test_public_dto_supplies_same_memberships_to_saved_client_filter():
    dto = summary_dto(JOINT)
    assert dto.affiliation_fields == ["Electrical and Computer Engineering", "Computer Science"]
    assert dto.affiliation_disciplines == ["Engineering", "Computing"]
    assert dto.field == dto.discipline == "Not publicly available"


def test_unknown_joint_department_is_not_invented():
    assert not field_filter_matches({"department": "Unknown One; Unknown Two"}, "Computing")


def test_single_department_still_uses_stored_field_metadata():
    assert not field_filter_matches({"department": "Computer Science", "field": "Bioengineering", "discipline": "Engineering"}, "Computing")
