# Official directory sources

V9 uses public professional information from official academic directories and linked faculty profiles.

## Existing connectors

- Stanford University — https://www.cs.stanford.edu/people/faculty
- University of California, Berkeley — https://www2.eecs.berkeley.edu/Faculty/Lists/CS/faculty.html
- University of California, Los Angeles — https://www.cs.ucla.edu/research-areas/
- University of California, San Diego — https://cse.ucsd.edu/people/faculty-profiles/faculty
- San Jose State University — https://www.sjsu.edu/cs/faculty/faculty.php
- University of Southern California — https://www.cs.usc.edu/directory/faculty/

## V9 connectors

- University of California, Davis — https://cs.ucdavis.edu/person-type/faculty (with official `/directory` and `/people` fallbacks)
- University of California, Irvine — https://cs.ics.uci.edu/faculty/ (Computer Science faculty section plus stable `https://ics.uci.edu/?people=<slug>` profiles)
- University of California, Santa Barbara — https://www.cs.ucsb.edu/people/faculty
- University of California, Santa Cruz — https://engineering.ucsc.edu/departments/computer-science-and-engineering/people/
- California Institute of Technology — https://www.cms.caltech.edu/people/faculty
- Santa Clara University — https://www.scu.edu/engineering/academic-programs/department-of-computer-engineering/faculty--staff/ and https://www.scu.edu/engineering/academic-programs/department-of-computer-engineering/faculty--staff-directory/
- California Polytechnic State University, San Luis Obispo — https://csc.calpoly.edu/faculty/ (the professor-level **Faculty** section only; affiliated faculty, emeriti, staff, office hours, and lecturer-only rows are excluded)
- San Diego State University — https://cs.sdsu.edu/faculty/

University layouts change over time. Use the owner refresh and targeted verification tools after importing a new source. Records without a public professional email are not saved.


## V9.4 authoritative refresh safety

UC Irvine and Cal Poly SLO are treated as authoritative rosters only during a full refresh. A full refresh prunes stale rows only after the rebuilt scraper returns at least its conservative minimum number of valid professor records. Small test refreshes never remove existing data.
