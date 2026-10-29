/** Copy pinned, locally installed browser libraries; Python serves the copies offline. */
import {createRequire} from 'node:module';
import {copyFileSync, mkdirSync} from 'node:fs';
import {dirname, join} from 'node:path';
const require=createRequire(new URL('../package.json',import.meta.url));
const mermaidRoot=dirname(require.resolve('mermaid/package.json'));
const dependency=createRequire(join(mermaidRoot,'package.json'));
const destination=new URL('./web/lib/',import.meta.url);
mkdirSync(destination,{recursive:true});
for(const [name,source,license] of [
  ['mermaid',join(mermaidRoot,'dist/mermaid.min.js'),join(mermaidRoot,'LICENSE')],
  ['marked',join(dirname(dependency.resolve('marked/package.json')),'lib/marked.umd.js'),join(dirname(dependency.resolve('marked/package.json')),'LICENSE.md')],
  ['purify',join(dirname(dependency.resolve('dompurify')),'purify.min.js'),join(dirname(dependency.resolve('dompurify')),'../LICENSE-MPL')],
]){
  copyFileSync(source,new URL(name+'.js',destination));
  copyFileSync(license,new URL(name+'.LICENSE.txt',destination));
}
