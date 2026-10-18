# Secondary page Chinese localization — source acceptance

This batch addresses the static-copy portion of LUC-F01. It translates existing
features, how-it-works, security, download, privacy, terms, refunds, contact,
referral and administrative labels using the existing browser-language policy.
Chinese browser variants use zh-CN; other languages keep English. Existing
legal terms, dates, referral amounts, permissions and download destinations are
preserved. No new legal commitment, paid-plan behavior or Profile restriction is
introduced. The translation is not a legal-policy revision or legal review.

The supplementary catalog and public-page script are separate modules. Public
pages reuse the shared translator and additionally translate titles and social
metadata. The dashboard retains its existing mutation observer. Dynamic expiry
labels use the existing wt lookup. Existing hosted route tests now require the
Chinese text instead of accepting English information/legal/admin headings.

Local verification: ten unittest cases passed, executing the actual shared
JavaScript through Node and checking complete static informational/legal/referral
text coverage, Chinese/English language selection, preserved referral amounts,
text-only transformations, metadata and JS syntax. DOM behavior uses a synthetic
minimal fixture; it is not a real-browser result. Local Chromium startup failed
before page execution with `socket() failed: Operation not permitted`; no launch
flag, permission or alternate route was used to bypass that restriction.

Hosted Chromium rendering/mobile layout and the whole current-candidate matrix
remain required. User-generated values, raw API error text, and machine-readable
status identifiers are not promised to be translated by this catalog. No real
Windows/device/provider/staging/production acceptance is claimed.

Independent review caught a dynamic standalone referral Copy success label
that lacked localization. It now calls wt and its actual async function is
executed in both English and Chinese Node fixtures.
