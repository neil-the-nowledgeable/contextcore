/*! For license information please see module.js.LICENSE.txt */
define(["@grafana/data","react","@grafana/runtime","@grafana/ui","@emotion/css"],(e,t,a,s,n)=>(()=>{"use strict";var r={7(e){e.exports=s},85(e,t,a){e.exports=a(335)},89(e){e.exports=n},335(e,t,a){var s=a(959),n=Symbol.for("react.element"),r=(Symbol.for("react.fragment"),Object.prototype.hasOwnProperty),o=s.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,l={key:!0,ref:!0,__self:!0,__source:!0};function i(e,t,a){var s,i={},c=null,d=null;for(s in void 0!==a&&(c=""+a),void 0!==t.key&&(c=""+t.key),void 0!==t.ref&&(d=t.ref),t)r.call(t,s)&&!l.hasOwnProperty(s)&&(i[s]=t[s]);if(e&&e.defaultProps)for(s in t=e.defaultProps)void 0===i[s]&&(i[s]=t[s]);return{$$typeof:n,type:e,key:c,ref:d,props:i,_owner:o.current}}t.jsx=i,t.jsxs=i},531(e){e.exports=a},781(t){t.exports=e},959(e){e.exports=t}},o={};function l(e){var t=o[e];if(void 0!==t)return t.exports;var a=o[e]={exports:{}};return r[e](a,a.exports,l),a.exports}l.d=(e,t)=>{for(var a in t)l.o(t,a)&&!l.o(e,a)&&Object.defineProperty(e,a,{enumerable:!0,get:t[a]})},l.o=(e,t)=>Object.prototype.hasOwnProperty.call(e,t),l.r=e=>{"undefined"!=typeof Symbol&&Symbol.toStringTag&&Object.defineProperty(e,Symbol.toStringTag,{value:"Module"}),Object.defineProperty(e,"__esModule",{value:!0})};var i={};l.r(i),l.d(i,{plugin:()=>m});var c=l(781),d=l(85),u=l(959),p=l(531),x=l(7),f=l(89);const h=()=>({container:f.css`
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px;
    height: 100%;
    overflow: auto;
  `,header:f.css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-weak);
  `,projectInfo:f.css`
    display: flex;
    gap: 8px;
    align-items: center;
  `,statusBadge:f.css`
    display: flex;
    align-items: center;
  `,label:f.css`
    font-size: 12px;
    color: var(--text-secondary);
  `,value:f.css`
    font-weight: 500;
    color: var(--text-primary);
  `,buttonRow:f.css`
    display: flex;
    gap: 8px;
  `,loadingSection:f.css`
    display: flex;
    justify-content: center;
    padding: 20px;
  `,stepsSection:f.css`
    background: var(--background-secondary);
    border-radius: 4px;
    padding: 12px;
  `,sectionTitle:f.css`
    font-weight: 500;
    font-size: 13px;
    margin-bottom: 8px;
    color: var(--text-primary);
  `,stepsList:f.css`
    display: flex;
    flex-direction: column;
    gap: 4px;
  `,step:f.css`
    display: flex;
    gap: 8px;
    align-items: center;
    font-size: 12px;
  `,stepStatus:f.css`
    width: 16px;
    text-align: center;
  `,stepName:f.css`
    color: var(--text-primary);
  `,stepReason:f.css`
    color: var(--text-secondary);
    font-style: italic;
  `,lastRunSection:f.css`
    background: var(--background-secondary);
    border-radius: 4px;
    padding: 12px;
  `,lastRunInfo:f.css`
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;

    > div {
      display: flex;
      gap: 8px;
    }
  `}),m=new c.PanelPlugin(({options:e,width:t,height:a})=>{const[s,n]=(0,u.useState)("idle"),[r,o]=(0,u.useState)(null),[l,i]=(0,u.useState)(null),[c,f]=(0,u.useState)(null),[m,y]=(0,u.useState)(!1),[g,v]=(0,u.useState)(null),[j,w]=(0,u.useState)(!1),b=(0,x.useStyles2)(h),_=(0,u.useRef)(null),S=(0,p.getTemplateSrv)().replace(e.projectId);(0,u.useEffect)(()=>("running"===s&&r&&e.refreshInterval>0&&(_.current=setInterval(async()=>{try{const t=await fetch(`${e.apiUrl}/trigger`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"beaver_workflow_status",payload:{run_id:r},context:{}})});if(t.ok){const e=await t.json();if("success"===e.status&&e.data){const t=e.data;i(t),"completed"===t.status?n("completed"):"failed"===t.status&&(n("failed"),v(t.error||"Workflow failed"))}}}catch(e){}},1e3*e.refreshInterval)),()=>{_.current&&(clearInterval(_.current),_.current=null)}),[s,r,e.apiUrl,e.refreshInterval]);const N=(0,u.useCallback)(async()=>{y(!0),v(null),f(null);try{const t=await fetch(`${e.apiUrl}/trigger`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"beaver_workflow_dry_run",payload:{project_id:S},context:{source:"grafana_panel"}})});if(!t.ok)throw new Error(`HTTP ${t.status}: ${t.statusText}`);const a=await t.json();if("success"===a.status){const e=a.data||{};f(e.steps||[]),o(a.run_id||e.run_id)}else v(a.message||"Dry run failed")}catch(e){v(e instanceof Error?e.message:"Failed to connect to Rabbit API")}finally{y(!1)}},[e.apiUrl,S]),R=(0,u.useCallback)(async()=>{e.confirmExecution?w(!0):await k()},[e.confirmExecution]),k=(0,u.useCallback)(async()=>{y(!0),v(null),n("running"),f(null);try{const t=await fetch(`${e.apiUrl}/trigger`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"beaver_workflow",payload:{project_id:S,dry_run:!1},context:{source:"grafana_panel"}})});if(!t.ok)throw new Error(`HTTP ${t.status}: ${t.statusText}`);const a=await t.json();if("success"===a.status){const e=a.data||{};o(e.run_id)}else v(a.message||"Failed to start workflow"),n("failed")}catch(e){v(e instanceof Error?e.message:"Failed to connect to Rabbit API"),n("failed")}finally{y(!1)}},[e.apiUrl,S]),I=(0,u.useCallback)(async()=>{w(!1),await k()},[k]),P=e=>new Date(e).toLocaleString();return(0,d.jsxs)("div",{className:b.container,style:{width:t,height:a},children:[(0,d.jsxs)("div",{className:b.header,children:[(0,d.jsxs)("div",{className:b.projectInfo,children:[(0,d.jsx)("span",{className:b.label,children:"Project:"}),(0,d.jsx)("span",{className:b.value,children:S})]}),(0,d.jsx)("div",{className:b.statusBadge,children:(()=>{switch(s){case"running":return(0,d.jsx)(x.Badge,{text:"Running",color:"blue",icon:"sync"});case"completed":return(0,d.jsx)(x.Badge,{text:"Completed",color:"green",icon:"check"});case"failed":return(0,d.jsx)(x.Badge,{text:"Failed",color:"red",icon:"exclamation-triangle"});default:return(0,d.jsx)(x.Badge,{text:"Idle",color:"purple"})}})()})]}),(0,d.jsxs)("div",{className:b.buttonRow,children:[e.showDryRun&&(0,d.jsx)(x.Button,{onClick:N,disabled:m||"running"===s,variant:"secondary",icon:"sync",children:"Dry Run"}),e.showExecute&&(0,d.jsx)(x.Button,{onClick:R,disabled:m||"running"===s,variant:"primary",icon:"play",children:"Execute"})]}),m&&(0,d.jsx)("div",{className:b.loadingSection,children:(0,d.jsx)(x.LoadingPlaceholder,{text:"Processing..."})}),g&&(0,d.jsx)(x.Alert,{severity:"error",title:"Error",children:g}),c&&(0,d.jsxs)("div",{className:b.stepsSection,children:[(0,d.jsx)("div",{className:b.sectionTitle,children:"Dry Run Preview"}),(0,d.jsx)("div",{className:b.stepsList,children:c.map((e,t)=>(0,d.jsxs)("div",{className:b.step,children:[(0,d.jsx)("span",{className:b.stepStatus,children:"would_execute"===e.status?"✓":"would_skip"===e.status?"○":"✗"}),(0,d.jsx)("span",{className:b.stepName,children:e.name}),e.reason&&(0,d.jsxs)("span",{className:b.stepReason,children:["(",e.reason,")"]})]},t))})]}),l&&(0,d.jsxs)("div",{className:b.lastRunSection,children:[(0,d.jsx)("div",{className:b.sectionTitle,children:"Last Run"}),(0,d.jsxs)("div",{className:b.lastRunInfo,children:[(0,d.jsxs)("div",{children:[(0,d.jsx)("span",{className:b.label,children:"Run ID:"}),(0,d.jsx)("span",{className:b.value,children:l.run_id})]}),(0,d.jsxs)("div",{children:[(0,d.jsx)("span",{className:b.label,children:"Started:"}),(0,d.jsx)("span",{className:b.value,children:P(l.started_at)})]}),l.completed_at&&(0,d.jsxs)("div",{children:[(0,d.jsx)("span",{className:b.label,children:"Completed:"}),(0,d.jsx)("span",{className:b.value,children:P(l.completed_at)})]}),void 0!==l.duration_seconds&&(0,d.jsxs)("div",{children:[(0,d.jsx)("span",{className:b.label,children:"Duration:"}),(0,d.jsx)("span",{className:b.value,children:(T=l.duration_seconds,T<60?`${T}s`:`${Math.floor(T/60)}m ${T%60}s`)})]}),(0,d.jsxs)("div",{children:[(0,d.jsx)("span",{className:b.label,children:"Progress:"}),(0,d.jsxs)("span",{className:b.value,children:[l.steps_completed,"/",l.steps_total," steps"]})]})]})]}),(0,d.jsx)(x.ConfirmModal,{isOpen:j,title:"Execute Workflow",body:`Are you sure you want to execute the workflow for project "${S}"?`,confirmText:"Execute",onConfirm:I,onDismiss:()=>w(!1)})]});var T}).setPanelOptions(e=>{e.addTextInput({path:"apiUrl",name:"Rabbit API URL",description:"Base URL of the Rabbit API server",defaultValue:"http://localhost:8080",category:["Connection"]}).addTextInput({path:"projectId",name:"Project ID",description:"Project ID or template variable (e.g., $project)",defaultValue:"$project",category:["Connection"]}).addBooleanSwitch({path:"showDryRun",name:"Show Dry Run Button",description:"Display the Dry Run button for previewing workflow execution",defaultValue:!0,category:["Buttons"]}).addBooleanSwitch({path:"showExecute",name:"Show Execute Button",description:"Display the Execute button for running workflows",defaultValue:!0,category:["Buttons"]}).addBooleanSwitch({path:"confirmExecution",name:"Confirm Execution",description:"Require confirmation before executing workflows",defaultValue:!0,category:["Buttons"]}).addNumberInput({path:"refreshInterval",name:"Auto-Refresh Interval",description:"Auto-refresh status interval in seconds (0 to disable)",defaultValue:10,category:["Display"]})});return i})());
//# sourceMappingURL=module.js.map