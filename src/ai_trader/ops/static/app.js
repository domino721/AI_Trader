'use strict';
let active = false, selected = null, refreshing = false;
const byId = id => document.getElementById(id);
const labels = {queued:'대기',pending:'대기',running:'실행 중',succeeded:'완료',failed:'실패',blocked:'후속 중단',interrupted:'중단 감지'};
const names = {verify_sources:'1. 원칙 문서 검증',build_index:'2. 검색 색인',evaluate_retrieval:'3. 고정 검색 평가',offline_model:'4. 모의 모델'};
const blockers = {live_transport_not_implemented:'실제 주문 연결 미구현',paper_observation_not_accepted:'브로커 모의매매 검증 미완료',strategy_validation_incomplete:'전략·백테스트 검증 미완료',broker_access_review_required:'계좌·API 접근권한 확인 필요',host_acceptance_not_recorded:'Windows PC 운영 수용 미완료',external_outage_alerts_not_configured:'PC 정지 외부 감시·알림 미연결',capital_not_configured:'투자금 미정',loss_limits_not_configured:'일손실·최대낙폭 한도 미정'};
const errors = {input_missing:'입력 자료 없음',validation_failed:'자료·평가 검증 실패',io_failed:'저장소 입출력 실패',step_failed:'단계 실행 실패',worker_heartbeat_expired:'실행기 응답 중단',worker_stopped:'실행기 종료',missed_schedule_slots:'예약 구간 누락',upstream_not_completed:'선행 단계 미완료'};
const element = (tag, text, cls) => {const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;};
const displayTime = value => value ? new Intl.DateTimeFormat('ko-KR',{dateStyle:'short',timeStyle:'medium',timeZone:'Asia/Seoul'}).format(new Date(value)) : '—';
function summary(step) {
  const value=step.summary;if(!value||step.status!=='succeeded')return '';
  if(step.name==='verify_sources')return value.documents+'개 문서 통과';
  if(step.name==='build_index')return value.chunks+'개 청크 · 스냅샷 '+value.snapshot_id.slice(0,12);
  if(step.name==='evaluate_retrieval')return value.total_cases+'개 고정 질의 중 '+value.passed_cases+'개 통과';
  if(step.name==='offline_model')return '모의 응답 완료 · 외부 호출 없음 · 실거래 승인 없음';
  return '';
}
async function api(path, options={}) {
  const headers={'Content-Type':'application/json',...(options.headers||{})};
  const token=byId('token').value;if(token)headers.Authorization='Bearer '+token;
  const response=await fetch(path,{...options,headers,credentials:'omit',cache:'no-store'});
  if(!response.ok)throw new Error(response.status===401?'접근 토큰을 확인하세요.':'요청 실패 ('+response.status+')');
  return response.json();
}
async function refresh() {
  if(!active||refreshing)return;refreshing=true;
  try {
    const [ready,runs,alerts]=await Promise.all([api('/ops/readiness'),api('/ops/runs'),api('/ops/alerts')]);
    byId('connection').textContent='연결됨 · 2초마다 갱신 · '+displayTime(new Date());
    const panel=byId('readiness');panel.replaceChildren(element('h2','환경: '+ready.environment));
    panel.append(element('p','연구 실행기: '+(ready.runtime_ready?'준비됨':'준비 확인 필요'),ready.runtime_ready?'good':'bad'));
    panel.append(element('p','실거래: 준비되지 않음','bad'));
    const reasons=element('ul','');for(const reason of ready.live_blockers)reasons.append(element('li',blockers[reason]||reason));panel.append(reasons);
    const tbody=byId('runs');tbody.replaceChildren();
    for(const run of runs){const row=element('tr','');const id=element('td','');const select=element('button',run.run_id,'select-run');select.addEventListener('click',()=>{selected=run.run_id;refresh();});id.append(select);row.append(id);for(const text of [labels[run.status]||run.status,displayTime(run.created_at),errors[run.error_code]||run.error_code||'—'])row.append(element('td',text));tbody.append(row);}
    if(!runs.length){const row=element('tr','');const empty=element('td','아직 실행 기록이 없습니다.');empty.colSpan=4;row.append(empty);tbody.append(row);}
    if(!selected&&runs.length)selected=runs[0].run_id;
    if(selected){const detail=await api('/ops/runs/'+encodeURIComponent(selected));byId('detail-title').textContent='단계별 진행 · '+selected;const graph=byId('graph');graph.replaceChildren();for(const step of detail.steps){const card=element('article','', 'step '+step.status);card.append(element('strong',names[step.name]||step.name),element('p',labels[step.status]||step.status),element('p','선행: '+(step.dependencies.map(name=>names[name]||name).join(', ')||'없음'),'muted'));if(step.error_code)card.append(element('p',errors[step.error_code]||step.error_code,'bad'));if(step.summary)card.append(element('p',summary(step),'muted'));graph.append(card);}}
    byId('alerts').replaceChildren(...(alerts.length?alerts.map(a=>element('li',displayTime(a.created_at)+' · '+a.run_id+' · '+(names[a.step]||'실행')+' · '+(errors[a.code]||a.code))):[element('li','저장된 경보가 없습니다.')]));
  } catch(error){byId('connection').textContent=error.message+' · 이전 표시를 최신 상태로 해석하지 마세요.';byId('readiness').replaceChildren(element('p','연결 실패 · 최신 준비 상태를 확인할 수 없습니다.','bad'));} finally{refreshing=false;}
}
byId('run-id').value='research-'+Date.now();
byId('connect').addEventListener('click',()=>{active=true;refresh();});
byId('run').addEventListener('click',async()=>{byId('run').disabled=true;try{await api('/ops/runs',{method:'POST',body:JSON.stringify({run_id:byId('run-id').value})});selected=byId('run-id').value;active=true;await refresh();}catch(error){byId('connection').textContent=error.message;}finally{byId('run').disabled=false;}});
setInterval(refresh,2000);
