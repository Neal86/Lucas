"""Actual admin JavaScript with a synthetic DOM/API, not browser acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from gpt_windows_connector.web_admin_runtime import ADMIN_SCRIPT


def execute(body, language='zh'):
    script = ADMIN_SCRIPT.split("if(WEB_LANG==='zh'){localizeWeb();", 1)[0]
    harness = r'''
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const timefmt=v=>String(v??''),wt=v=>v;
const state={user:{}},loginGeneration=1;
const adminContent={innerHTML:''},adminUserDetail={innerHTML:''};
const adminUserModal={classList:{remove(){},add(){},contains(){return false}}};
const document={getElementById(id){return id==='adminUserDetail'?adminUserDetail:adminUserModal},querySelectorAll(){return []}};
const operationUsageHtml=()=>'',unresolvedOperationsHtml=()=>'';
'''
    return json.loads(subprocess.check_output(['node','-e', 'const WEB_LANG='+json.dumps(language)+';'+harness+script+'\n(async()=>{'+body+'})().catch(e=>{console.error(e);process.exit(1)});'],text=True,encoding='utf-8'))


class AdminEnumLabelTests(unittest.TestCase):
    def test_context_specific_labels_and_english_identity(self):
        cases=[['role','super_admin'],['account','active'],['plan','free'],['plan','pro_plus'],['operation','failed'],['subscription','active']]
        body='console.log(JSON.stringify('+json.dumps(cases)+'.map(([kind,value])=>adminEnumLabel(kind,value))))'
        self.assertEqual(execute(body),['超级管理员','正常','免费','Pro+','失败','有效'])
        self.assertEqual(execute(body,'en'),[x[1] for x in cases])

    def test_unknown_and_prototype_keys_are_unchanged(self):
        body='console.log(JSON.stringify([adminEnumLabel("role","toString"),adminEnumLabel("role","<new>"),adminEnumLabel("missing","active"),adminEnumLabel("plan",null)]))'
        self.assertEqual(execute(body),['toString','<new>','active',None])

    def test_user_table_translates_enum_only(self):
        row={'id':'fixture','email':'active','name':'free','role':'admin','status':'disabled','plan':'pro_plus','node_count':1,'operations_30d':2}
        body='console.log(JSON.stringify(renderAdminUsers(['+json.dumps(row)+'])))'
        rendered=execute(body)
        for label in ['管理员','已停用','Pro+','<b>active</b>','>free</div>']:self.assertIn(label,rendered)
        self.assertIn('<td>disabled</td>',execute(body,'en'))

    def test_operations_escape_unknown_status_and_user_content(self):
        rows=[{'status':'success','email':'success','action':'success','target':'<unsafe>'},{'status':'<script>','action':'unchanged'}]
        html=execute('console.log(JSON.stringify(renderAdminOps('+json.dumps(rows)+')))')
        self.assertIn('<td>成功</td>',html)
        self.assertIn('<td>success</td>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('&lt;unsafe&gt;',html)
        self.assertNotIn('<script>',html)

    def test_detail_option_values_and_selected_state_preserved(self):
        data={'user':{'id':'fixture','email':'free','role':'user','status':'disabled'},'entitlements':{},'usage':{},'subscription':{'plan':'pro_plus'},'nodes':[],'operations':[]}
        html=execute('renderAdminUserDetail('+json.dumps(data)+');console.log(JSON.stringify(adminUserDetail.innerHTML))')
        for value,label in [('active','正常'),('disabled','已停用'),('free','免费'),('pro','Pro'),('pro_plus','Pro+')]:
            selected='selected' if value in ('disabled','pro_plus') else ''
            self.assertIn(f'<option value="{value}" {selected}>{label}</option>',html)
        self.assertIn('<h3>free</h3>',html)
        self.assertIn('<div>用户</div>',html)

    def test_subscription_tab_labels_preserve_provider_and_unknown(self):
        data={'subscriptions':[{'email':'active','plan':'free','status':'active','billing_provider':'stripe'},{'plan':'future-plan','status':'<future>'}]}
        body='globalThis.api=async()=>('+json.dumps(data)+');await adminTab("subscriptions",null,false);console.log(JSON.stringify(adminContent.innerHTML))'
        html=execute(body)
        for label in ['<td>免费</td>','<td>有效</td>','<td>active</td>','<td>stripe</td>','future-plan','&lt;future&gt;']:self.assertIn(label,html)
        self.assertIn('<td>free</td>',execute(body,'en'))


if __name__=='__main__':unittest.main()
