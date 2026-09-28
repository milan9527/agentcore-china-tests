<!DOCTYPE html>
        <!DOCTYPE HTML><html xmlns="http://www.w3.org/1999/xhtml"><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"><title>Amazon Bedrock AgentCore</title><meta xmlns="" name="subtitle" content="Developer Guide"><meta http-equiv="refresh" content="0;URL=what-is-bedrock-agentcore.html"><script type="text/javascript"><!--
        var myDefaultPage = "what-is-bedrock-agentcore.html";
           	var myPage = document.location.search.substr(1);
           	var myHash = document.location.hash;

              // Allowlist a single .html file name in this directory, optionally
              // followed by further query parameters. Anything else falls back to
              // the default page. The raw value is validated: location.search is
              // not percent decoded, so %5C and similar never become separators.
              //
              // Percent escapes are allowed only for bytes 0x80 and above, which is
              // what a browser sends for a non ASCII file name: the Well-Architected
              // Maori lens ships 8 pages whose names contain U+0101, sent as %C4%81.
              // Keeping the escape to high bytes leaves every ASCII escape rejected
              // right here, so %5C, %2F, %3A and %00 never reach the URL parser.
              var docfile = /^((?:[A-Za-z0-9._~-]|%[89A-Fa-f][0-9A-Fa-f])+\.html)(?:&|$)/.exec(myPage);
              var target = docfile ? docfile[1] : myDefaultPage;

              // Defense in depth: ask the URL parser where the value actually
              // resolves rather than predicting it, and reject anything that
              // leaves this origin or this directory.
              if (typeof URL === "function") {
                 var dir = new URL(".", document.location.href);
                 var to = new URL(target + myHash, dir);
                 if (to.origin !== dir.origin || to.pathname.indexOf(dir.pathname) !== 0) {
                    to = new URL(myDefaultPage, dir);
                 }
                 self.location.replace(to.href);
              } else {
                 self.location.replace(target + myHash);
              }
    --></script></head><body></body></html>