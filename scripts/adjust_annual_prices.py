from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

repls = {
    ROOT / 'src/gpt_windows_connector/billing_ui.py': {
        "Annual <span class=\"save\">Save 20%</span>": "Annual <span class=\"save\">Save ~17%</span>",
        "Pay monthly at regular price, or annually and save 20%.": "Pay monthly at regular price, or annually and save about 17%.",
        "$95.90": "$99.99",
        "$191.90": "$199.99",
        "$143.90": "$149.99",
    },
    ROOT / 'src/gpt_windows_connector/web_billing_runtime.py': {
        "$95.90": "$99.99",
        "$191.90": "$199.99",
        "$143.90/yr": "$149.99/yr",
    },
    ROOT / 'src/gpt_windows_connector/billing.py': {
        "out['billing_total']=round(monthly*12*0.8,2) if interval=='year' else round(monthly,2)\n        out['monthly_equivalent']=round(monthly*0.8,2) if interval=='year' else round(monthly,2)": "annual_base={'free':0.0,'pro':99.99,'pro_plus':199.99}[ent.plan]\n        annual_total=annual_base+ent.expansion_quantity*149.99\n        out['billing_total']=round(annual_total,2) if interval=='year' else round(monthly,2)\n        out['monthly_equivalent']=round(annual_total/12,2) if interval=='year' else round(monthly,2)"
    },
}

for path, mapping in repls.items():
    text = path.read_text(encoding='utf-8')
    old = text
    for a, b in mapping.items():
        if a not in text:
            raise SystemExit(f'missing expected text in {path.name}: {a}')
        text = text.replace(a, b)
    path.write_text(text, encoding='utf-8')
    print(f'updated {path.relative_to(ROOT)}')
