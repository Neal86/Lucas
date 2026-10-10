import asyncio
import pytest
from gpt_windows_connector import browser_semantic
from gpt_windows_connector.browser_targets import observe_page, reference_target, unique_visible

class Handle:
    def __init__(self, text='Save', visible=True):
        self.item = dict(tag='button', text=text, visible=visible, connected=True, disabled=False)
        self.disposed = self.clicked = False
    async def evaluate(self, _):
        if self.disposed: raise RuntimeError('disposed')
        return dict(self.item)
    async def dispose(self): self.disposed = True
    async def is_visible(self): return self.item['visible']
    async def scroll_into_view_if_needed(self, **_): pass
    async def click(self, **_): self.clicked = True
    async def fill(self, text, **_): self.value = text

class Locator:
    def __init__(self, handles): self.handles = handles
    async def element_handles(self): return self.handles
    async def count(self): return len(self.handles)
    def nth(self, index): return self.handles[index]

class Page:
    url = 'https://example.com'
    def __init__(self, handles): self.handles = handles
    def locator(self, _): return Locator(self.handles)
    async def title(self): return 'Example'

def test_hidden_nodes_do_not_consume_limit_and_refs_are_exact():
    async def run():
        hidden, first, second = Handle(visible=False), Handle(), Handle()
        page = Page([hidden, first, second])
        result = await observe_page(page, 2)
        assert len(result['elements']) == 2
        ref = result['elements'][1]['ref']
        page.handles.insert(0, Handle('New button'))
        assert await reference_target(page, ref) is second
        assert hidden.disposed
    asyncio.run(run())

@pytest.mark.parametrize('change', ['connected', 'visible', 'text', 'disabled'])
def test_changed_reference_stops_before_click(change):
    async def run():
        handle = Handle(); page = Page([handle])
        ref = (await observe_page(page))['elements'][0]['ref']
        handle.item[change] = 'Delete' if change == 'text' else change == 'disabled'
        with pytest.raises(LookupError): await reference_target(page, ref)
        assert not handle.clicked
    asyncio.run(run())

def test_reference_cannot_cross_tabs_or_observations():
    async def run():
        page = Page([Handle()])
        ref = (await observe_page(page))['elements'][0]['ref']
        with pytest.raises(LookupError): await reference_target(Page([]), ref)
        page.handles = [Handle()]; await observe_page(page)
        with pytest.raises(LookupError): await reference_target(page, ref)
    asyncio.run(run())

def test_semantic_reference_reaches_handler(monkeypatch):
    async def run():
        handle = Handle(); page = Page([handle])
        monkeypatch.setattr(browser_semantic.browser, '_page', lambda *args: page)
        ref = (await browser_semantic.observe('session'))['elements'][0]['ref']
        result = await browser_semantic.semantic_click('session', ref)
        assert result['strategy'] == 'element-ref' and handle.clicked
        await browser_semantic.semantic_type('session', ref, 'hello')
        assert handle.value == 'hello'
    asyncio.run(run())

def test_ambiguous_visible_controls_are_rejected():
    async def run():
        with pytest.raises(LookupError, match='Ambiguous'):
            await unique_visible(Locator([Handle(), Handle()]), 'Save')
        only = Handle()
        assert await unique_visible(Locator([Handle(visible=False), only]), 'Save') is only
    asyncio.run(run())
