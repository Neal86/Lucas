"""Account-owned dashboard event sockets and their reconnect timers.

These guards only suppress obsolete browser callbacks. They do not change
server event authorization, device permissions or dispatched operations.
"""
from __future__ import annotations

REALTIME_SCRIPT = r'''
let eventSocket=null,eventSocketOwner=null,eventReconnectTimer=null,eventHeartbeatTimer=null,eventWatchdogTimer=null,eventEverConnected=false,eventReconnectDelay=1000,eventLastAck=0,eventGeneration=0;
function clearRealtimeTimers(){
  clearTimeout(eventReconnectTimer);clearInterval(eventHeartbeatTimer);clearInterval(eventWatchdogTimer);
  eventReconnectTimer=eventHeartbeatTimer=eventWatchdogTimer=null;
}
function stopRealtime(){
  eventGeneration++;clearRealtimeTimers();eventEverConnected=false;
  const socket=eventSocket;eventSocket=null;eventSocketOwner=null;
  if(socket){socket.onopen=socket.onmessage=socket.onerror=socket.onclose=null;try{socket.close()}catch{}}
}
function scheduleRealtimeReconnect(){
  if(!state.user||eventReconnectTimer)return;
  const generation=eventGeneration,login=loginGeneration,user=state.user;
  const delay=Math.min(eventReconnectDelay,30000);eventReconnectDelay=Math.min(eventReconnectDelay*2,30000);
  const timer=setTimeout(()=>{
    if(eventReconnectTimer!==timer||eventGeneration!==generation||loginGeneration!==login||state.user!==user)return;
    eventReconnectTimer=null;startRealtime();
  },delay+Math.floor(Math.random()*350));
  eventReconnectTimer=timer;
}
function startRealtime(){
  if(!state.user)return;
  if(eventSocket&&eventSocketOwner?.()&&(eventSocket.readyState===WebSocket.OPEN||eventSocket.readyState===WebSocket.CONNECTING))return;
  if(eventSocket)stopRealtime();
  clearTimeout(eventReconnectTimer);eventReconnectTimer=null;
  const generation=++eventGeneration,login=loginGeneration,user=state.user;
  const protocol=location.protocol==='https:'?'wss:':'ws:';
  const socket=new WebSocket(`${protocol}//${location.host}/ws/events`);
  eventSocket=socket;
  const owns=()=>eventSocket===socket&&eventGeneration===generation&&loginGeneration===login&&state.user===user;
  eventSocketOwner=owns;
  socket.onopen=()=>{
    if(!owns())return;
    const recovered=eventEverConnected;eventEverConnected=true;eventReconnectDelay=1000;eventLastAck=Date.now();
    clearInterval(eventHeartbeatTimer);clearInterval(eventWatchdogTimer);
    eventHeartbeatTimer=setInterval(()=>{if(owns()&&socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'heartbeat'}))},20000);
    eventWatchdogTimer=setInterval(()=>{if(owns()&&socket.readyState===WebSocket.OPEN&&Date.now()-eventLastAck>55000)socket.close(4000,'heartbeat timeout')},10000);
    if(recovered)refresh(owns).catch(()=>{});
  };
  socket.onmessage=e=>{
    if(!owns())return;
    eventLastAck=Date.now();let message;try{message=JSON.parse(e.data)}catch{return}
    if(message.type==='node.upsert')applyNodeUpsert(message.node);
    else if(message.type==='node.remove')refresh(owns).catch(()=>{});
  };
  socket.onerror=()=>{};
  socket.onclose=()=>{
    if(!owns())return;
    eventSocket=null;eventSocketOwner=null;
    clearInterval(eventHeartbeatTimer);clearInterval(eventWatchdogTimer);eventHeartbeatTimer=eventWatchdogTimer=null;
    scheduleRealtimeReconnect();
  };
}
'''
