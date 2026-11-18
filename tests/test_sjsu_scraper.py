from scrapers.sjsu import extract_sjsu_website_url, parse_sjsu_directory_html


SJSU_HTML = """
<html><body><table>
<tr><th>Faculty</th><th>Research Interests</th></tr>
<tr>
  <td><a href="/people/sayma-akther">Sayma Akther</a><br>
      Assistant Professor<br>(408) 924-2511<br>
      <a href="mailto:sayma.akther@sjsu.edu">sayma.akther@sjsu.edu</a></td>
  <td>Artificial Intelligence (AI) and Machine Learning, Data Science and Analytics, Generative AI</td>
</tr>
<tr>
  <td><a href="https://www.cs.sjsu.edu/~stamp/">Mark Stamp</a><br>
      Professor<br>mark.stamp@sjsu.edu</td>
  <td>Information security, Machine Learning</td>
</tr>
</table></body></html>
"""


def test_parse_sjsu_directory_extracts_public_fields():
    entries = parse_sjsu_directory_html(SJSU_HTML)
    by_name = {entry.name: entry for entry in entries}
    assert set(by_name) == {"Sayma Akther", "Mark Stamp"}
    assert by_name["Sayma Akther"].title == "Assistant Professor"
    assert by_name["Sayma Akther"].email == "sayma.akther@sjsu.edu"
    assert "Generative AI" in by_name["Sayma Akther"].research_interests
    assert by_name["Mark Stamp"].website_url == "https://www.cs.sjsu.edu/~stamp/"


def test_sjsu_profile_extracts_lab_or_personal_site():
    html = """
    <html><body>
      <a href="https://example-lab.sjsu.edu/">Research Lab</a>
      <a href="https://scholar.google.com/example">Google Scholar</a>
    </body></html>
    """
    assert (
        extract_sjsu_website_url(html, "https://www.sjsu.edu/people/example")
        == "https://example-lab.sjsu.edu/"
    )


def test_sjsu_removes_image_suffix_from_lecturer_name():
    html = """
    <html><body><table><tr>
      <td><a href="/cs/faculty/lecturers.php"><img alt="Benjamin Poon image">Benjamin Poon image</a>
      Lecturer <a href="mailto:ben.poon@sjsu.edu">ben.poon@sjsu.edu</a></td>
      <td>Artificial Intelligence in Education, Software Engineering</td>
    </tr></table></body></html>
    """
    entries = parse_sjsu_directory_html(
        html,
        "https://www.sjsu.edu/cs/faculty/lecturers.php",
        "Lecturer",
    )
    assert len(entries) == 1
    assert entries[0].name == "Benjamin Poon"
