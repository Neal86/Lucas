"""Exercise production checklist/hint callbacks across account and UI lifecycles."""
from __future__ import annotations

import json

import pytest

from test_computer_onboarding_runtime import isolated_settings, run_computer_js


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("transition", [
    "state.user={email:'next@example.test'};",
    "state.user={email:state.user.email};",
    "loginGeneration++;",
    "hideGettingStarted();state.user=null;loginGeneration++;auth.classList.remove('hidden');app.classList.add('hidden');",
], ids=["different-account", "same-email-replacement", "new-login-generation", "logout"])
def test_delayed_hint_cannot_cross_its_authenticated_session(language, transition):
    run_computer_js("""
signIn();stored.set('unrelated-draft','keep');maybeStartOnboarding();flushMutations();
document.getElementById('coachClose').onclick();
const delayed=timeouts.find(t=>t.delay===120).f;
const before=[...stored];
""" + transition + """
// Also exercise an already-queued callback after cancellation, not just clearTimeout.
delayed();runTimers(120);
assert.deepEqual([...stored],before);
assert.equal(!!document.getElementById('coachReopenHint'),false);
assert.equal(gettingStartedNav.classList.contains('lucas-reopen-target'),false);
assert.equal(stored.has('lucas-setup-checklist-hint-v1:guest'),false);
assert.equal(requests.length,0);assert.equal(routes.length,0);
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_logout_cancels_delayed_hint_before_next_account_opens(language):
    run_computer_js("""
signIn();openGettingStarted();flushMutations();document.getElementById('coachClose').onclick();
const oldShow=timeouts.find(t=>t.delay===120);
let unrelated=0;const unrelatedTimer=setTimeout(()=>unrelated++,120);
hideGettingStarted();loginGeneration++;state.user={email:'next@example.test'};
assert.equal(timeouts.some(t=>t.id===oldShow.id),false);
assert.equal(timeouts.some(t=>t.id===unrelatedTimer),true);
openGettingStarted();flushMutations();const currentClose=document.getElementById('coachClose').onclick;
oldShow.f();runTimers(120);
assert.equal(unrelated,1);assert.equal(document.getElementById('lucasCoach').style.display,'block');
assert.equal(!!document.getElementById('coachReopenHint'),false);
assert.equal(stored.has('lucas-setup-checklist-hint-v1:next@example.test'),false);
currentClose();runTimers(120);
assert.ok(document.getElementById('coachReopenHint'));
assert.equal(stored.get('lucas-setup-checklist-v1:next@example.test'),'1');
assert.equal(stored.get('lucas-setup-checklist-hint-v1:next@example.test'),'1');
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_reopening_cancels_queued_hint_and_old_close_without_cancelling_other_timers(language):
    run_computer_js("""
signIn();openGettingStarted();flushMutations();const oldClose=document.getElementById('coachClose').onclick;
oldClose();const oldShow=timeouts.find(t=>t.delay===120);
let unrelated=0;const unrelatedTimer=setTimeout(()=>unrelated++,120);
openGettingStarted();flushMutations();
assert.equal(timeouts.some(t=>t.id===oldShow.id),false);
assert.equal(timeouts.some(t=>t.id===unrelatedTimer),true);
oldShow.f();oldClose();runTimers(120);
assert.equal(unrelated,1);assert.equal(document.getElementById('lucasCoach').style.display,'block');
assert.equal(!!document.getElementById('coachReopenHint'),false);
assert.equal(stored.has('lucas-setup-checklist-hint-v1:synthetic@example.test'),false);
// A current close still creates the account's once-only hint.
document.getElementById('coachClose').onclick();runTimers(120);
assert.ok(document.getElementById('coachReopenHint'));
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_old_hint_timer_and_button_cannot_dismiss_replacement_hint(language):
    run_computer_js("""
signIn();openGettingStarted();flushMutations();document.getElementById('coachClose').onclick();runTimers(120);
const oldHint=document.getElementById('coachReopenHint');
const oldButton=oldHint.querySelector('button').onclick,oldDismiss=timeouts.find(t=>t.delay===9000);
let unrelated=0;const unrelatedTimer=setTimeout(()=>unrelated++,9000);
hideGettingStarted();loginGeneration++;state.user={email:'next@example.test'};
assert.equal(timeouts.some(t=>t.id===oldDismiss.id),false);
assert.equal(timeouts.some(t=>t.id===unrelatedTimer),true);
openGettingStarted();flushMutations();document.getElementById('coachClose').onclick();runTimers(120);
const currentHint=document.getElementById('coachReopenHint'),before=[...stored];
assert.ok(currentHint);assert.notEqual(currentHint,oldHint);
const currentDismiss=timeouts.find(t=>t.delay===9000&&t.id!==unrelatedTimer);
oldDismiss.f();oldButton();
assert.equal(document.getElementById('coachReopenHint')===currentHint,true);
assert.equal(gettingStartedNav.classList.contains('lucas-reopen-target'),true);
assert.equal(timeouts.some(t=>t.id===currentDismiss.id),true);assert.deepEqual([...stored],before);
currentHint.querySelector('button').onclick();
assert.equal(!!document.getElementById('coachReopenHint'),false);
assert.equal(gettingStartedNav.classList.contains('lucas-reopen-target'),false);
assert.equal(timeouts.some(t=>t.id===currentDismiss.id),false);
runTimers(9000);assert.equal(unrelated,1);assert.deepEqual([...stored],before);
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("transition", [
    "openGettingStarted();",
    "onboardingSync();",
], ids=["reopen", "rerender"])
def test_detached_checklist_buttons_cannot_close_or_navigate_new_checklist(language, transition):
    run_computer_js("""
signIn();stored.set('unrelated-draft','keep');openGettingStarted();flushMutations();
const oldClose=document.getElementById('coachClose').onclick;
const oldStep=document.getElementById('lucasCoach').querySelectorAll('.coach-step')[0].onclick;
""" + transition + """
flushMutations();const before=[...stored],currentClose=document.getElementById('coachClose').onclick;
oldClose();oldStep();runTimers(120);
assert.equal(document.getElementById('lucasCoach').style.display,'block');
assert.equal(document.getElementById('coachClose').onclick,currentClose);
assert.equal(routes.length,0);assert.equal(!!document.getElementById('coachReopenHint'),false);
assert.deepEqual([...stored],before);
// The current button is deliberately allowed to navigate and record dismissal.
document.getElementById('lucasCoach').querySelectorAll('.coach-step')[0].onclick();
assert.equal(routes.length,1);assert.equal(routes[0].id,'ai');
assert.equal(document.getElementById('lucasCoach').style.display,'none');
assert.equal(stored.get('lucas-setup-checklist-v1:'+state.user.email),'1');
assert.equal(stored.get('unrelated-draft'),'keep');assert.equal(timeouts.some(t=>t.delay===120),false);
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("transition", [
    "state.user={email:'next@example.test'};",
    "state.user={email:state.user.email};",
    "loginGeneration++;",
], ids=["different-account", "same-email-replacement", "new-login-generation"])
def test_session_change_alone_invalidates_checklist_callbacks_and_sync_cleans_ui(language, transition):
    run_computer_js("""
signIn();openGettingStarted();flushMutations();
const oldClose=document.getElementById('coachClose').onclick;
const oldStep=document.getElementById('lucasCoach').querySelectorAll('.coach-step')[1].onclick;
""" + transition + """
const user=state.user;oldClose();oldStep();finishOnboarding();runTimers(120);
assert.equal(state.user,user);assert.equal(stored.size,0);assert.equal(routes.length,0);
assert.equal(!!document.getElementById('coachReopenHint'),false);
onboardingSync();assert.equal(document.getElementById('lucasCoach').style.display,'none');
openGettingStarted();flushMutations();finishOnboarding();runTimers(120);
assert.ok(document.getElementById('coachReopenHint'));
""", language)


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_current_hint_auto_dismissal_localization_once_only_keys_and_completion_rule(language):
    expected = ("You can reopen setup guidance here anytime.", "Got it") if language == "en" else (
        "你可以随时在这里重新打开设置指南。", "知道了")
    run_computer_js("""
signIn();stored.set('unrelated-draft','keep');
state.aiClients=[{client_id:'ai-test'}];state.nodes=[{authorized:true,online:false}];
maybeStartOnboarding();assert.equal(!!document.getElementById('lucasCoach'),false);
// Explicit reopen remains available even when the existing completion rule is met.
openGettingStarted();flushMutations();
assert.deepEqual(document.getElementById('lucasCoach').querySelectorAll('.coach-step').map(b=>b.classList.contains('done')),[true,true,true]);
finishOnboarding();runTimers(120);const hint=document.getElementById('coachReopenHint');assert.ok(hint);
""" + f"""
assert.ok(hint.textContent.includes({json.dumps(expected[0])}));
assert.equal(hint.querySelector('button').textContent,{json.dumps(expected[1])});
""" + """
const before=[...stored];runTimers(9000);
assert.equal(!!document.getElementById('coachReopenHint'),false);
assert.equal(gettingStartedNav.classList.contains('lucas-reopen-target'),false);
openGettingStarted();flushMutations();finishOnboarding();runTimers(120);
assert.equal(!!document.getElementById('coachReopenHint'),false);assert.deepEqual([...stored],before);
assert.equal(stored.get('lucas-setup-checklist-v1:synthetic@example.test'),'1');
assert.equal(stored.get('lucas-setup-checklist-hint-v1:synthetic@example.test'),'1');
assert.equal(stored.get('unrelated-draft'),'keep');assert.equal(requests.length,0);
""", language)
