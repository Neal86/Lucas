from __future__ import annotations

from .web_landing_brand import LANDING_NAV_TEXT_COLOR

LANDING_HEADER_STYLE = r'''<style>
.landing-nav{
  position:fixed!important;top:0;left:0;right:0;z-index:1000!important;
  height:82px;width:100%;max-width:none;margin:0;
  padding-left:max(28px,calc((100vw - 1240px)/2 + 28px))!important;
  padding-right:max(28px,calc((100vw - 1240px)/2 + 28px))!important;
  display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid rgba(255,255,255,.07);
  background:rgba(5,7,13,.88);
  backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
  box-shadow:0 1px 0 rgba(255,255,255,.06)
}
.landing-nav>.landing-logo{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:760;letter-spacing:-.02em}
.landing-nav>.landing-logo img{display:block;width:220px;height:52px;object-fit:contain;object-position:left center;filter:none!important;opacity:1!important;background:transparent!important;padding:0!important}
.landing-links{display:flex;gap:34px}
.landing-links a{color:__LANDING_NAV_TEXT_COLOR__;font-size:13px;text-decoration:none;transition:.2s}
.landing-links a:hover{color:#fff}
.landing-signin{color:#dfe4f3;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.11);border-radius:10px;padding:10px 15px;cursor:pointer}
.mobile-menu{display:none}
@media(max-width:800px){
  .landing-nav{position:fixed!important;top:0!important;left:0!important;right:0!important;inset-inline:0!important;height:66px!important;width:100vw!important;max-width:100vw!important;padding:0 16px!important;display:grid!important;grid-template-columns:42px 1fr auto;align-items:center;background:#05070d!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;transform:translateZ(0);-webkit-transform:translateZ(0);will-change:transform}
  .landing-nav>.landing-logo{position:absolute;left:50%;transform:translateX(-50%);display:flex;align-items:center;justify-content:center;z-index:1;pointer-events:none}
  .landing-nav>.landing-logo img{width:132px!important;max-width:132px!important;height:auto!important}
  .landing-nav>.landing-links{display:none!important}
  .landing-nav>.landing-signin{display:inline-flex!important;grid-column:3;align-items:center;justify-content:center;justify-self:end;position:relative;z-index:4;min-width:78px;height:42px;padding:0 12px;border-radius:11px;background:linear-gradient(110deg,#6473f4,#5969e9);color:#fff;border:0;font-size:13px;font-weight:700}
  .mobile-menu{display:block;grid-column:1;position:relative;z-index:3;margin:0;padding:0}
  .mobile-menu summary{list-style:none;width:42px;height:42px;border:0;border-radius:0;background:transparent;display:grid;place-items:center;cursor:pointer;color:#eef2ff;font-size:0}
  .mobile-menu summary::-webkit-details-marker{display:none}
  .mobile-menu summary:before{content:'☰';font-size:26px;line-height:1;font-weight:500}
  .mobile-menu[open] summary:before{content:'×';font-size:27px;font-weight:300}
  .mobile-menu-panel{position:fixed;top:66px;left:12px;right:12px;padding:12px;background:rgba(10,13,22,.97);border:1px solid rgba(255,255,255,.11);border-radius:16px;box-shadow:0 22px 60px rgba(0,0,0,.48);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);display:flex;flex-direction:column;gap:4px}
  .mobile-menu-panel a,.mobile-menu-panel button{width:100%;min-height:48px;padding:12px 14px;border-radius:10px;text-align:left;color:#dfe4f3;text-decoration:none;font:600 15px/1.2 Inter,ui-sans-serif,system-ui;background:transparent;border:0}
  .mobile-menu-panel a:active{background:rgba(255,255,255,.07)}
  .mobile-menu-panel .mobile-signin{margin-top:6px;text-align:center;background:linear-gradient(110deg,#6473f4,#5969e9);color:#fff;cursor:pointer}
}
@media(max-width:390px){
  .landing-nav>.landing-logo img{width:118px!important;max-width:118px!important}
}
</style>'''.replace("__LANDING_NAV_TEXT_COLOR__", LANDING_NAV_TEXT_COLOR)
