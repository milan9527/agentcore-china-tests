import React from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserLiveView} from 'bedrock-agentcore/browser/live-view';
import dcv from 'dcv';

window.probe = {authenticated: false, connected: false, firstFrame: false, errors: []};
window.dcv = dcv;
window.renderLive = signedUrl => createRoot(document.getElementById('root')).render(
  <BrowserLiveView signedUrl={signedUrl} remoteWidth={1280} remoteHeight={720}/>
);
