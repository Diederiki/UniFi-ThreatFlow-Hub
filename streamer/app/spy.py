"""The JavaScript spy injected into every console tab via CDP at
document_start.

The spy hooks RTCPeerConnection.prototype.createDataChannel + the
'datachannel' event, copies binary payloads from the
`ws:/proxy/network/wss/...` data channels into base64-encoded entries
in `window.__streamer.dc`, and exposes a drain function so Python can
poll the buffer and flush it.

Why hook the prototype rather than replace the constructor:
the page bundle grabs `RTCPeerConnection` once at module-init time, so
Constructor-replacement is a no-op. The prototype path catches every
PeerConnection regardless of how it was constructed.
"""
SPY_SOURCE = r"""
(() => {
  if (window.__streamer) return;
  window.__streamer = { dc: [], started_at: Date.now(), last_seen: 0, any_count: 0, ws_opens: [] };

  // Hook WebSocket so we can see open/close codes — if the AWS IoT
  // MQTT WS keeps reconnecting, the close codes tell us why.
  try {
    const oWS = window.WebSocket;
    const Wrapped = function(url, protocols) {
      const ws = new oWS(url, protocols);
      const u = String(url || '');
      // host+path only, drop signed query string so JSON stays small
      const host = u.replace(/\?.*$/, '');
      const idx = window.__streamer.ws_opens.length;
      window.__streamer.ws_opens.push({
        ts: Date.now(), host: host, opened: false, closeCode: null, closeReason: null
      });
      ws.addEventListener('open',  () => { try { window.__streamer.ws_opens[idx].opened = true; } catch(_){} });
      ws.addEventListener('close', (ev) => { try {
        window.__streamer.ws_opens[idx].closeCode = ev.code;
        window.__streamer.ws_opens[idx].closeReason = String(ev.reason || '').slice(0, 60);
      } catch(_){} });
      ws.addEventListener('error', () => { try { window.__streamer.ws_opens[idx].error = true; } catch(_){} });
      return ws;
    };
    Wrapped.prototype = oWS.prototype;
    Wrapped.CONNECTING = oWS.CONNECTING;
    Wrapped.OPEN = oWS.OPEN;
    Wrapped.CLOSING = oWS.CLOSING;
    Wrapped.CLOSED = oWS.CLOSED;
    window.WebSocket = Wrapped;
  } catch(e) {}

  // Hide common automation tells. Ubiquiti's WebRTC negotiation refuses
  // to connect when navigator.webdriver is true; the rest are belt-and-
  // braces against feature detection.
  try {
    Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined });
  } catch(e) {}
  try {
    if (!window.chrome) window.chrome = { runtime: {} };
  } catch(e) {}
  // navigator.languages occasionally empty in headless — populate.
  try {
    Object.defineProperty(Navigator.prototype, 'languages', { get: () => ['en-US', 'en'] });
  } catch(e) {}
  // permissions.query returning 'denied' for everything also flags us.
  try {
    const oQuery = navigator.permissions && navigator.permissions.query;
    if (oQuery) {
      navigator.permissions.query = (p) => p && p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : oQuery.call(navigator.permissions, p);
    }
  } catch(e) {}
  if (typeof RTCPeerConnection === 'undefined') return;
  const proto = RTCPeerConnection.prototype;

  // Buffer ONLY the events-channel binary frames (those carry the
  // IDS/IPS/firewall stream we ingest). Every other WS-tunnelled frame
  // (dashboard:sync, client:sync, device:sync, api:N…) just bumps a
  // last-seen timestamp so Python can tell "the WebRTC peer is alive"
  // from "we got security data". Storing all frames blew up tab memory
  // around 50+ tabs.
  function pushFrame(label, data) {
    if (!(data instanceof ArrayBuffer)) return;
    if (!String(label).startsWith('ws:/')) return;
    window.__streamer.last_seen = Date.now();
    window.__streamer.any_count += 1;
    if (!String(label).includes('/events?') && !String(label).endsWith('/events')) return;
    const bytes = new Uint8Array(data, 0, Math.min(data.byteLength, 65536));
    let bin = '';
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    window.__streamer.dc.push({ label: label, sample: btoa(bin), ts: Date.now() });
  }

  function hookDC(dc) {
    if (dc.__streamerHooked) return;
    dc.__streamerHooked = true;
    dc.addEventListener('message', (ev) => pushFrame(dc.label, ev.data));
  }

  // Stamp every PeerConnection with a state log so we can see ICE/DTLS
  // negotiation outcome from Python.
  window.__streamer.pc_states = [];
  function watchPC(pc) {
    if (pc.__streamerWatched) return;
    pc.__streamerWatched = true;
    const idx = window.__streamer.pc_states.length;
    window.__streamer.pc_states.push({
      ts: Date.now(), transitions: [],
      ice: pc.iceConnectionState, conn: pc.connectionState, sig: pc.signalingState,
    });
    const tx = (label) => { try { window.__streamer.pc_states[idx].transitions.push({
      t: Date.now() - window.__streamer.pc_states[idx].ts, label,
      ice: pc.iceConnectionState, conn: pc.connectionState, sig: pc.signalingState,
    }); } catch(_){} };
    pc.addEventListener('iceconnectionstatechange', () => tx('ice'));
    pc.addEventListener('connectionstatechange',    () => tx('conn'));
    pc.addEventListener('signalingstatechange',     () => tx('sig'));
    pc.addEventListener('icegatheringstatechange',  () => tx('gather'));
    pc.addEventListener('icecandidateerror',        (ev) => {
      try { window.__streamer.pc_states[idx].transitions.push({
        t: Date.now() - window.__streamer.pc_states[idx].ts, label: 'ice-err',
        code: ev.errorCode, text: String(ev.errorText||'').slice(0,80),
      }); } catch(_){}
    });
  }

  const oCreate = proto.createDataChannel;
  proto.createDataChannel = function(label, init) {
    watchPC(this);
    const dc = oCreate.call(this, label, init);
    hookDC(dc);
    return dc;
  };
  const oSetRemote = proto.setRemoteDescription;
  proto.setRemoteDescription = function(desc) {
    watchPC(this);
    const self = this;
    self.addEventListener('datachannel', (ev) => hookDC(ev.channel));
    return oSetRemote.apply(this, arguments);
  };

  // Drain function Python invokes from page.evaluate(); returns and
  // empties the buffer atomically.
  window.__streamerDrain = function() {
    const out = window.__streamer.dc;
    window.__streamer.dc = [];
    return out;
  };
  // Tiny health probe Python uses to detect dead/stale tabs.
  window.__streamerStats = function() {
    return {
      started_at: window.__streamer.started_at,
      buffered: window.__streamer.dc.length,
      now: Date.now(),
    };
  };
})();
"""
