import real from './nice-dcv-web-client-sdk/dcvjs-esm/dcv.js';
export default {
  ...real,
  authenticate(url, callbacks) {
    window.probeEvent?.('authenticate.start');
    return real.authenticate(url, {...callbacks,
      success(a,r) {
        window.probe.authenticated=true;
        window.probeEvent?.('authenticate.success', {sessionCount:r?.length,
          authTokenPresent:Boolean(r?.[0]?.authToken)});
        callbacks.success?.(a,r);
      },
      error(a,e) {
        const message=String(e.message||e);
        window.probe.errors.push(message);
        window.probeEvent?.('authenticate.error', {message});
        callbacks.error?.(a,e);
      }
    });
  },
  connect(options) {
    window.probeEvent?.('connect.start');
    const field=options.observers ? 'observers' : 'callbacks';
    const callbacks=options[field]||{};
    return real.connect({...options,[field]:{...callbacks,
      firstFrame(...args) {
        window.probe.firstFrame=true;
        window.probeEvent?.('display.firstFrame');
        callbacks.firstFrame?.(...args);
      },
      disconnect(...args) {
        window.probeEvent?.('connect.disconnect');
        callbacks.disconnect?.(...args);
      }
    }}).then(c=>{
      window.probe.connected=true; window.connection=c;
      window.probeEvent?.('connect.success');
      return c;
    }).catch(e=>{
      const message=String(e.message||e);
      window.probe.errors.push(message);
      window.probeEvent?.('connect.error', {message});
      throw e;
    });
  }
};
