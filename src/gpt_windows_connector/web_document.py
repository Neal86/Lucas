from __future__ import annotations

import os

META_PIXEL_ID = "1406185724930401"
META_PIXEL_HEAD = '<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version="2.0";n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,"script","https://connect.facebook.net/en_US/fbevents.js");fbq("init","'+META_PIXEL_ID+'");fbq("track","PageView");window.lucasMetaTrack=function(event,params,eventId){try{if(window.fbq){if(eventId)fbq("track",event,params||{},{eventID:eventId});else fbq("track",event,params||{})}}catch(_){}};window.lucasMetaTrackOnce=function(key,event,params,eventId){try{const k="lucas_meta_"+key;if(sessionStorage.getItem(k))return;sessionStorage.setItem(k,"1");window.lucasMetaTrack(event,params,eventId)}catch(_){window.lucasMetaTrack(event,params,eventId)}};</script>'

GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", "").strip()
GA4_HEAD = (
    '<script async src="https://www.googletagmanager.com/gtag/js?id='+GA_MEASUREMENT_ID+'"></script>'
    '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)};gtag("js",new Date());gtag("config","'+GA_MEASUREMENT_ID+'");window.lucasGaTrack=function(event,params){try{if(window.gtag)gtag("event",event,params||{})}catch(_){}};</script>'
    if GA_MEASUREMENT_ID.startswith("G-") else ""
)
TRACKING_HEAD = META_PIXEL_HEAD + GA4_HEAD

WEB_HEAD = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8" />\n<meta name="viewport" content="width=device-width,initial-scale=1" />\n<title>Lucas</title>\n<link rel="icon" type="image/png" sizes="32x32" href="/assets/lucas-logo-square.png?v=20260908" />\n<link rel="shortcut icon" type="image/png" href="/assets/lucas-logo-square.png?v=20260908" />\n<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>\n' + TRACKING_HEAD + '\n'

WEB_BODY_PREFIX = '\n</head>\n<body>\n'
