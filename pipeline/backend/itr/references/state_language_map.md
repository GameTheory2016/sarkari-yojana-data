# Which languages cover which states

Use this to pick a language set. Codes match `languages.md` and `itr.py`.

## Recommended sets

| Set | Languages | Reach |
|---|---|---|
| Minimum | en, hi | Most of the north and the Hindi belt, plus English everywhere |
| Tier 1 (13) | en, hi, bn, mr, te, ta, gu, ur, kn, or, ml, pa, as | The main language of every large state, about 95% of people |
| Every state | Tier 1 + kok, ne, mni, lus, kha, ks, doi | Each state and UT also gets its own language |
| Full 22 scheduled | Every state + mai, sat, brx, sd, sa | All Eighth Schedule languages (Sanskrit, sa, is rarely worth shipping) |

Start with Tier 1. Add tier 2 languages only when the app targets that state,
because each needs native review.

## State by state

| State or UT | Main language | Also used |
|---|---|---|
| Andhra Pradesh | te | ur |
| Arunachal Pradesh | en (official) | hi |
| Assam | as | bn (Barak Valley), brx (Bodoland) |
| Bihar | hi | ur, mai |
| Chhattisgarh | hi | Chhattisgarhi (written in Devanagari, Hindi works) |
| Goa | kok | mr |
| Gujarat | gu | hi |
| Haryana | hi | pa |
| Himachal Pradesh | hi | Sanskrit (official, rarely needed) |
| Jharkhand | hi | sat, ur, bn, or |
| Karnataka | kn | ur, te, ta |
| Kerala | ml | |
| Madhya Pradesh | hi | |
| Maharashtra | mr | hi, ur |
| Manipur | mni | en |
| Meghalaya | en (official) | kha, grt |
| Mizoram | lus | en |
| Nagaland | en (official) | Nagamese (a Latin-script creole, no standard form) |
| Odisha | or | sat |
| Punjab | pa | hi |
| Rajasthan | hi | |
| Sikkim | ne | en |
| Tamil Nadu | ta | |
| Telangana | te | ur |
| Tripura | bn | trp |
| Uttar Pradesh | hi | ur |
| Uttarakhand | hi | Sanskrit |
| West Bengal | bn | ne (hills), ur, sat |
| Andaman & Nicobar | hi, en | bn, ta, te |
| Chandigarh | en, hi | pa |
| Dadra & Nagar Haveli and Daman & Diu | gu, hi | mr |
| Delhi | hi | pa, ur |
| Jammu & Kashmir | ur, ks, doi, hi, en | |
| Ladakh | hi, en | Ladakhi (Tibetan script, rarely supported) |
| Lakshadweep | ml | en |
| Puducherry | ta | ml (Mahe), te (Yanam), en |

## Notes

- Hindi plus English is a sensible fallback anywhere in the north and north-east.
- Urdu is a second official language in UP, Bihar, Telangana, Andhra
  Pradesh, Jharkhand, West Bengal, Delhi and J&K. It is worth shipping for
  government or welfare apps aimed at those states.
- In the language picker, show each language's own name in its own script
  (हिन्दी, ગુજરાતી, தமிழ், اردو), with the English name beside it.
