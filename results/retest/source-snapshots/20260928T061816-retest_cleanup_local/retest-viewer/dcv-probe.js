import real from './nice-dcv-web-client-sdk/dcvjs-esm/dcv.js';
export default {
  ...real,
  authenticate(url, callbacks) {
    return real.authenticate(url, {...callbacks,
      success(a,r) { window.probe.authenticated=true; callbacks.success?.(a,r); },
      error(a,e) { window.probe.errors.push(String(e.message||e)); callbacks.error?.(a,e); }
    });
  },
  connect(options) {
    const field=options.observers ? 'observers' : 'callbacks';
    const callbacks=options[field]||{};
    return real.connect({...options,[field]:{...callbacks,
      firstFrame(...args) { window.probe.firstFrame=true; callbacks.firstFrame?.(...args); }
    }}).then(c=>{ window.probe.connected=true; window.connection=c; return c; })
      .catch(e=>{ window.probe.errors.push(String(e.message||e)); throw e; });
  }
};
