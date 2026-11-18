# UCLA parser fixtures

The profile fragments were retrieved from these public pages on 2026-10-05 (HTTP 200):

- https://samueli.ucla.edu/people/aditya-grover/
- https://samueli.ucla.edu/people/kai-wei-chang/
- https://samueli.ucla.edu/people/yuchen-cui/

These are trimmed HTML fixtures, not screenshots or complete page captures. The actual `.seas-profile` identity and research accordion markup is retained. Images, SVGs, unrelated accordions and non-email contact details were removed. The surrounding blank logo heading, Bioengineering/Expert Directory navigation and footer are reconstructed minimal reproductions of the observed template hazards.

Kai-Wei Chang's identity header says Professor; his biography says Associate Professor. The parser test verifies extraction from the appointment header. It does not resolve that source conflict or authorize changing the stored rank.

Expanded review: `profile-129/133/135/141/143/162.html` retain only the actual
identity fragments fetched on 2026-10-05. Contact blocks, links and icons are
removed; the blank heading/navigation wrapper is reconstructed. These cover
joint departments, reviewed nickname/spelling variants, teaching/emeritus ranks,
Unicode names and an explicitly future-dated appointment. Their public source
URLs and capture hashes are in the expanded review evidence.

Kai-Wei Chang's university-hosted personal page was subsequently retrieved and
also states Professor. The expanded staging report records that corroboration;
the initial fixture remains unchanged as historical evidence of the conflict.
