import React from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserLiveView} from 'bedrock-agentcore/browser/live-view';
import dcv from 'dcv';

window.probe = {authenticated: false, connected: false, firstFrame: false, errors: [], events: []};
window.probeStarted = performance.now();
window.probeEvent = (event, details = {}) => window.probe.events.push({
  event, time: new Date().toISOString(),
  elapsedSeconds: Number(((performance.now() - window.probeStarted) / 1000).toFixed(3)),
  ...details,
});
window.dcv = dcv;
window.renderLive = signedUrl => createRoot(document.getElementById('root')).render(
  <BrowserLiveView signedUrl={signedUrl} remoteWidth={1280} remoteHeight={720}/>
);
