const {createRequire}=require('node:module');
const {join}=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const root=process.env.DSH_RUNTIME_ROOT;
 if(!root)throw Error('Set DSH_RUNTIME_ROOT to the installed DSH runtime directory containing node_modules.');
 const req=createRequire(join(root,'package.json'));
 const {Context}=await import(pathToFileURL(req.resolve('@deepseek-ai/cordis')).href);
 const skill=await import(pathToFileURL(req.resolve('@deepseek-ai/dsh-skill')).href);
 const plugin=await import(pathToFileURL(join(__dirname,'../index.mjs')).href);
 const ctx=new Context();
 await ctx.plugin(skill.default);
 await ctx.plugin(plugin);
 const list=await ctx.skills.list();
 const loaded=await ctx.skills.get('zotero');
 if(!list.some(s=>s.name==='zotero')||!loaded?.content.includes('run-zotero.mjs')||loaded.content.includes('{{ZOTERO_RUNNER_PS}}'))throw Error('registry validation failed');
 console.log(JSON.stringify({runtime:process.versions.node,skill:list.find(s=>s.name==='zotero'),loaded:true}));
 // This isolated registry check creates no timers, processes or external resources.
})().catch(e=>{console.error(e);process.exitCode=1});
