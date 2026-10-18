# Administrative enum display validation

Candidate based on ec6c09b52f5a550a54fcaa6f8be58bd46eaa9219.

F01 confirmed remaining copy: administrative user tables and detail role/status/plan labels, operation status, subscription plan/status were raw English enum identifiers. The context-only helper translates known Chinese labels at these display sites. Unknown values are retained and escaped by the existing esc function; email/name/action/target/provider are not translated. Option values and account mutation payloads remain unchanged. Historical Pro/Pro+ administrative data is display-only; Beta-free public product rules are unchanged.

Validation: python -m unittest discover -s tests -p test_admin_enum_labels.py -v — 6 passed locally. Node executes the actual administrative JavaScript with synthetic DOM/API responses. Cases cover Chinese/English, contextual active labels, unknown/prototype keys, HTML escaping, user-content preservation, dropdown values/selected state, subscription rendering. These do not prove real-browser layout, all dynamic copy, actual accounts/providers, or full F01 acceptance. Exact-head hosted CI still required.
