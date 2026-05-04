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
  window.__streamer = { dc: [], started_at: Date.now() };
  if (typeof RTCPeerConnection === 'undefined') return;
  const proto = RTCPeerConnection.prototype;

  function pushFrame(label, data) {
    if (!(data instanceof ArrayBuffer)) return;
    if (!String(label).startsWith('ws:/proxy/network/wss/s/')) return;
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

  const oCreate = proto.createDataChannel;
  proto.createDataChannel = function(label, init) {
    const dc = oCreate.call(this, label, init);
    hookDC(dc);
    return dc;
  };
  const oSetRemote = proto.setRemoteDescription;
  proto.setRemoteDescription = function(desc) {
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
