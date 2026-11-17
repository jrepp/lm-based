import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function page() {
  const elements = new Map();
  const element = () => ({
    textContent:'',style:{},hidden:false,children:[],attributes:{},
    classList:{add(){},remove(){},toggle(){}},
    append(...nodes){this.children.push(...nodes);},
    get firstChild(){return this.children[0];},get lastChild(){return this.children.at(-1);},
    setAttribute(key,value){this.attributes[key]=value;},remove(){},
    getBoundingClientRect(){return {width:800,height:320};},
    getContext(){return new Proxy({}, {get:()=>()=>{}});},
  });
  let now = 100000;
  class Clock extends Date {static now(){return now;}}
  let response = {models:[{id:'qwen',state:'ready',snapshot:{observed_at:new Date(now).toISOString(),sample_count:2,window_seconds:30,rates:{predicted_tokens_per_second:11},slots:[]},rolling:{context:200,cache:50}}]};
  let failure = false;
  const storage = new Map([['dashboard-model','qwen']]);
  const context = vm.createContext({Date:Clock,Intl,Map,Set,console,
    document:{getElementById(id){if(!elements.has(id)) elements.set(id,element());return elements.get(id);},createElement:element},
    localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    window:{devicePixelRatio:1,addEventListener(){},setTimeout(){}},
    fetch:async()=>{if(failure)throw new Error('offline');return {ok:true,status:200,json:async()=>structuredClone(response)};},
  });
  vm.runInContext(readFileSync(new URL('./assets/app.js',import.meta.url),'utf8'),context);
  return {elements, context, response, tick(ms){now+=ms;},fail(value){failure=value;},refresh:()=>vm.runInContext('refresh()',context)};
}

test('rolling summary holds for five seconds while preserving model button identity',async()=>{
 const p=page();await p.refresh();
 const button=p.elements.get('model-list').children[0];
 assert.equal(p.elements.get('decode-rate').textContent,'11');
 p.tick(1000);p.response.models[0].snapshot.rates.predicted_tokens_per_second=99;
 await p.refresh();assert.equal(p.elements.get('decode-rate').textContent,'11');
 assert.equal(p.elements.get('model-list').children[0],button);
 p.tick(5000);await p.refresh();assert.equal(p.elements.get('decode-rate').textContent,'99');
});

test('discovery outage and missing model retain selection, cards and history',async()=>{
 const p=page();await p.refresh();
 p.fail(true);await p.refresh();
 assert.equal(p.elements.get('selected-model').textContent,'qwen');
 assert.equal(p.elements.get('model-detail').hidden,false);
 assert.match(p.elements.get('model-notice').textContent,/History retained/);
 p.fail(false);p.response.models=[];await p.refresh();
 assert.equal(p.elements.get('selected-model').textContent,'qwen');
 assert.equal(p.elements.get('model-detail').hidden,false);
 assert.equal(p.elements.get('decode-rate').textContent,'11');
});
