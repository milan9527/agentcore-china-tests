import * as esbuild from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
const root = path.dirname(new URL(import.meta.url).pathname);
const sdk = path.join(root,'node_modules/bedrock-agentcore/dist/src/tools/browser/live-view/nice-dcv-web-client-sdk');
fs.cpSync(sdk,path.join(root,'nice-dcv-web-client-sdk'),{recursive:true});
await esbuild.build({entryPoints:[path.join(root,'main.jsx')],bundle:true,outfile:path.join(root,'bundle.js'),
 alias:{dcv:path.join(root,'dcv-probe.js'),'dcv-ui':path.join(sdk,'dcv-ui/dcv-ui.js')},
 define:{'process.env.NODE_ENV':'"production"'},logLevel:'warning'});
