"use client";

import { useEffect, useState } from "react";
import { RequireAuth } from "@/components/auth/SignInPrompt";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";
import { apiFetch, ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth-context";

type Report = { days:number; started_at:string|null; enabled:boolean; registered_accounts:number; rows:{day:string;metric:string;count:number}[]; limitations:string };
const labels:Record<string,string>={searches:"Search requests",recommendation_requests:"Recommendation requests",profile_saves:"Profile updates",researchers_saved:"Save actions",outreach_updates:"Outreach updates",resume_previews:"Résumé previews"};

export default function UsagePage() {
  const {user} = useAuth();
  const [days,setDays]=useState(30);
  const [loaded,setLoaded]=useState<{owner:string;report:Report}|null>(null);
  const result=loaded?.owner===user?.user_id ? loaded?.report??null : null;
  const [error,setError]=useState("");
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    if(!user) return;
    const controller=new AbortController();
    apiFetch<Report>(`/api/usage/summary?days=${days}`,{signal:controller.signal})
      .then(value=>{if(!controller.signal.aborted){setLoaded({owner:user.user_id,report:value});setError("");}})
      .catch(reason=>{if(!controller.signal.aborted){setLoaded(null);setError(reason instanceof ApiError ? reason.message : "Usage reports are temporarily unavailable.");}});
    return ()=>controller.abort();
  },[user,days,retry]);
  const totals:Record<string,number>={};
  for(const row of result?.rows??[]) totals[row.metric]=(totals[row.metric]??0)+row.count;
  return <RequireAuth><Container className="py-10 sm:py-12">
    <PageHeader title="Website usage" description="Private owner report. Aggregate activity, not individual visitor tracking." />
    <label className="mt-6 block text-sm font-medium">Reporting period <select value={days} onChange={e=>{setDays(Number(e.target.value));setLoaded(null);setError("");}} className="ml-3 rounded-control border border-border bg-surface p-2"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select></label>
    {error ? <div role="alert" className="card mt-6 p-5"><p>{error}</p><button className="focus-ring mt-3 underline" onClick={()=>setRetry(v=>v+1)}>Try again</button></div> : !result ? <p role="status" className="mt-6">Loading usage report…</p> : <>
      <div className="mt-6 grid gap-4 sm:grid-cols-2"><div className="card p-5"><p>Total registered Google accounts</p><p className="mt-2 text-3xl font-semibold">{result.registered_accounts}</p><p className="mt-2 text-sm text-slate-500">All-time accounts still stored, including your own. This is not an active-user count.</p></div><div className="card p-5"><p>Measured page views in this period</p><p className="mt-2 text-3xl font-semibold">{Object.entries(totals).filter(([k])=>k.startsWith("page:")).reduce((sum,[,v])=>sum+v,0)}</p><p className="mt-2 text-sm text-slate-500">Repeat visits count again. Browser privacy preferences, blockers and scripts affect coverage.</p></div></div>
      <p className="mt-6 text-sm text-slate-500">{result.enabled ? "Collection enabled." : "Collection disabled."} {result.started_at ? `First aggregate collected: ${new Date(result.started_at).toLocaleString()}.` : "No activity collected yet."} Older visits cannot be reconstructed.</p>
      <div className="card mt-6 overflow-x-auto p-5"><table className="w-full text-left text-sm"><caption className="mb-4 text-left font-semibold">Activity totals — last {result.days} days</caption><thead><tr><th scope="col" className="py-2">Activity</th><th scope="col" className="py-2 text-right">Count</th></tr></thead><tbody>{Object.entries(totals).sort(([a],[b])=>a.localeCompare(b)).map(([key,value])=><tr key={key} className="border-t border-border"><td className="py-3">{key.startsWith("page:") ? `Page: ${key.slice(5).replaceAll("_"," ")}` : labels[key]??key}</td><td className="py-3 text-right">{value}</td></tr>)}</tbody></table>{!Object.keys(totals).length?<p>No measured activity in this period.</p>:null}</div>
      <p className="mt-5 max-w-3xl text-sm text-slate-500">{result.limitations}</p>
    </>}
  </Container></RequireAuth>;
}
