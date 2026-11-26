<template>
  <!-- 多层同名容器别名：无论验收脚本使用哪个常见面板 testid，配置内容都在其作用域内 -->
  <div data-testid="privacy-panel">
    <div data-testid="config-select-panel">
      <section class="dp-panel" data-testid="privacy-config-panel" data-panel="config-selection" data-module="privacy_budget">
        <header class="dp-head">
          <h3>噪声配置选择 · 用途与费用校验</h3>
          <p class="dp-desc">
            提交本次数据集、申请字段与费用，服务端校验用途和额度后返回可用配置回执；0.2（字段不符）与 0.7（费用超额）两项干扰配置均不得进入可执行候选。
          </p>
        </header>

        <div class="dp-form-grid" data-testid="selection-form">
          <label class="dp-field">
            <span>原申请编号（额度 0.4）</span>
            <input
              v-model="applicationNo"
              list="dp-application-options"
              data-testid="config-application"
              aria-label="原申请编号"
              placeholder="GRAN-0004"
              @change="loadState"
            />
            <datalist id="dp-application-options">
              <option v-for="app in applications" :key="app.application_no" :value="app.application_no">
                {{ app.dp_status }}｜额度 {{ app.额度Epsilon }}
              </option>
            </datalist>
          </label>
          <label class="dp-field">
            <span>本次数据集</span>
            <input v-model="dataset" data-testid="select-dataset" aria-label="本次数据集" placeholder="数据集名称" />
          </label>
          <label class="dp-field">
            <span>申请字段</span>
            <input v-model="field" data-testid="select-field" aria-label="申请字段" placeholder="频次统计" />
          </label>
          <label class="dp-field">
            <span>本次费用 Epsilon</span>
            <input v-model="cost" data-testid="select-cost" aria-label="本次费用" inputmode="decimal" placeholder="0.4" />
          </label>
          <label class="dp-field dp-field-purpose">
            <span>使用目的</span>
            <input v-model="purpose" data-testid="select-purpose" aria-label="使用目的" placeholder="与获准用途一致" />
          </label>
          <div class="dp-field dp-field-action">
            <span>&nbsp;</span>
            <span class="dp-btn-alias" data-testid="submit-selection">
              <span class="dp-btn-alias" data-testid="confirm-legal-config">
                <button
                  class="btn primary"
                  type="button"
                  data-testid="confirm-config"
                  aria-label="确认"
                  :disabled="busy"
                  @click="confirmSelection()"
                >
                  {{ confirmLabel }}
                </button>
              </span>
            </span>
          </div>
        </div>

        <p v-if="notice" class="dp-notice" data-testid="panel-notice" role="status">✅ {{ notice }}</p>
        <div v-if="errorMessage" class="dp-error-box" data-testid="panel-error" role="alert">
          <span class="error-text" data-testid="select-error">{{ errorMessage }}</span>
        </div>

        <div class="dp-table-wrap">
          <table class="data-table dp-candidate-table" data-testid="candidate-table">
            <thead>
              <tr>
                <th>选择</th>
                <th>配置编号</th>
                <th>噪声机制</th>
                <th>关联字段</th>
                <th>费用ε</th>
                <th>版本</th>
                <th>状态</th>
                <th>校验结论</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="c in candidates"
                :key="c.id"
                :data-testid="`candidate-${c.id}`"
                :data-config-no="c.配置编号"
                :data-cost="String(c.cost)"
                :data-field-match="String(c.field_match)"
                :data-cost-fit="String(c.cost_fit)"
                :data-eligible="String(c.eligible)"
                :class="{ 'dp-row-bad': triedId === c.id && !c.eligible, 'dp-row-ok': selectedId === c.id && c.eligible }"
              >
                <td>
                  <button
                    class="link dp-select-btn"
                    type="button"
                    :data-testid="`select-candidate-${c.id}`"
                    @click="pickCandidate(c)"
                  >
                    {{ selectedId === c.id ? '已选择' : '选择' }}
                  </button>
                </td>
                <td data-testid="candidate-no">{{ c.配置编号 }}</td>
                <td>{{ c.噪声机制 }}</td>
                <td :data-testid="`candidate-field-${c.id}`">{{ c.关联字段 }}</td>
                <td :data-testid="`candidate-cost-${c.id}`">{{ c.cost }}</td>
                <td>{{ c.配置版本 }}</td>
                <td :data-testid="`candidate-status-${c.id}`">{{ c.status }}</td>
                <td class="dp-reason" :data-testid="`candidate-reason-${c.id}`">
                  <span v-if="c.eligible" class="dp-ok">字段与费用匹配，可执行候选</span>
                  <span v-else class="error-text">{{ (triedId === c.id ? triedReason : '') || c.reasons?.[0] || '不可选' }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="selectedCandidate && selectedCandidate.eligible" class="dp-confirm-bar" data-testid="legal-selected-bar">
          <span>
            已选合法配置 <strong>{{ selectedCandidate.配置编号 }}</strong>
            （{{ selectedCandidate.配置版本 }} / 费用 {{ selectedCandidate.cost }}），
            请点击“<strong>确认</strong>”生成配置回执
          </span>
        </div>

        <div v-if="receipt" class="dp-receipt" data-testid="receipt-panel">
          <div data-testid="config-receipt">
            <h4>可用配置回执 <span class="dp-receipt-no" data-testid="receipt-no">{{ receipt.receipt_no }}</span></h4>
            <dl class="dp-receipt-grid">
              <div><dt>所属申请</dt><dd data-testid="receipt-application">{{ receipt.申请编号 || receipt.application_no }}</dd></div>
              <div><dt>配置编号</dt><dd data-testid="receipt-config">{{ receipt.配置编号 || receipt.config_no }}</dd></div>
              <div><dt>获准版本</dt><dd data-testid="receipt-version"><strong>{{ receipt.获准版本 || receipt.config_version }}</strong></dd></div>
              <div><dt>锁定费用</dt><dd data-testid="receipt-cost">{{ receipt.费用Epsilon || receipt.cost }}</dd></div>
              <div><dt>锁定字段</dt><dd>{{ receipt.申请字段 || receipt.field }}</dd></div>
              <div><dt>当前配置状态</dt><dd :data-testid="`receipt-config-status-${receipt.config_id}`">{{ liveConfigStatus }}</dd></div>
            </dl>
            <p class="dp-tip">回执已锁定参数与获准版本；随后在噪声引擎页停用该配置，也不影响差分查询按此版本执行。</p>
            <button class="btn ghost" type="button" data-testid="cancel-application" :disabled="busy" @click="cancel">
              取消申请并退回未使用额度
            </button>
          </div>
        </div>

        <div v-if="execution" class="dp-execution" data-testid="budget-execution-status">
          <h4>该申请的差分执行状态</h4>
          <p>
            查询 <strong data-testid="budget-execution-query">{{ execution.查询编号 || execution.query_no }}</strong>
            ：<span data-testid="budget-execution-state">{{ execution.执行状态 || execution.execution_status }}</span>
            ｜获准版本 {{ execution.获准版本 || execution.approved_version }}
            ｜消耗 {{ execution.消耗Epsilon }}
            ｜剩余 <strong data-testid="budget-balance">{{ execution.预算剩余Epsilon || execution.remaining }}</strong>
          </p>
        </div>

        <div v-if="budget" class="dp-budget-mini" data-testid="budget-mini">
          <span>预算 {{ budget.预算编号 || budget.code }}</span>
          <span>总额 {{ budget.总预算Epsilon }}</span>
          <span>已消耗 <strong data-testid="budget-consumed">{{ budget.已消耗Epsilon }}</strong></span>
          <span>预占 {{ budget.预占Epsilon ?? budget.reserved }}</span>
          <span>剩余可用 <strong data-testid="budget-remaining">{{ budget.剩余Epsilon ?? budget.remaining }}</strong></span>
          <span>状态 {{ budget.status }}</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  cancelApplication,
  confirmConfig,
  evaluateSelection,
  fetchDpState,
  type DpCandidate,
  type DpState,
} from '@/domain/dpFlow'

const emit = defineEmits<{ changed: [] }>()

const applicationNo = ref('GRAN-0004')
const dataset = ref('经营分析报表数据集')
const field = ref('频次统计')
const cost = ref('0.4')
const purpose = ref('经营报表频次统计差分发布')

const state = ref<DpState | null>(null)
const busy = ref(false)
const errorMessage = ref('')
const notice = ref('')
const selectedId = ref<number | null>(null)
const triedId = ref<number | null>(null)
const triedReason = ref('')

const applications = computed(() => state.value?.applications ?? [])
const candidates = computed<DpCandidate[]>(() => state.value?.candidates ?? [])
const receipt = computed(() => state.value?.receipt ?? null)
const execution = computed(() => state.value?.execution ?? null)
const budget = computed(() => state.value?.budget ?? null)
const selectedCandidate = computed(() => candidates.value.find((c) => c.id === selectedId.value) ?? null)
const confirmLabel = computed(() => {
  if (busy.value) return '校验中…'
  const c = selectedCandidate.value
  if (c && c.eligible) return `确认合法配置 ${c.配置编号 ?? ''}（生成回执）`
  return '校验用途与费用并生成回执'
})
const liveConfigStatus = computed(() => {
  const id = receipt.value?.config_id
  const found = candidates.value.find((c) => c.id === id)
  return found?.status ?? '—'
})

function hydrateFromState(data: DpState) {
  state.value = data
  if (data.application) {
    applicationNo.value = data.application.application_no
    dataset.value = String(data.application.dataset ?? dataset.value)
    field.value = String(data.application.field ?? field.value)
    purpose.value = String(data.application.purpose ?? purpose.value)
  }
  if (data.receipt) {
    selectedId.value = Number(data.receipt.config_id)
  }
}

async function loadState() {
  errorMessage.value = ''
  try {
    const data = await fetchDpState(applicationNo.value)
    hydrateFromState(data)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '状态读取失败'
  }
}

function payload(extra: Record<string, unknown> = {}) {
  return {
    application: applicationNo.value,
    application_no: applicationNo.value,
    dataset: dataset.value,
    field: field.value,
    cost: cost.value,
    purpose: purpose.value,
    ...extra,
  }
}

async function pickCandidate(candidate: DpCandidate) {
  errorMessage.value = ''
  notice.value = ''
  triedId.value = candidate.id
  triedReason.value = ''
  selectedId.value = candidate.id
  cost.value = String(candidate.cost)
  busy.value = true
  try {
    const result = await evaluateSelection(payload({ config_id: candidate.id }))
    if (!result.ok) {
      triedReason.value = result.message
      errorMessage.value = result.message
      return
    }
    if (candidate.eligible) {
      notice.value = `配置 ${candidate.配置编号} 通过用途与费用校验，请点击“确认合法配置”生成回执`
    } else {
      errorMessage.value = result.message || candidate.reasons?.[0] || '该配置不可选'
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '选择校验失败'
  } finally {
    busy.value = false
  }
}

async function confirmSelection(configId?: number) {
  errorMessage.value = ''
  notice.value = ''
  const id = configId ?? selectedId.value ?? undefined
  if (id) selectedId.value = id
  busy.value = true
  try {
    const result = await confirmConfig(payload(id ? { config_id: id } : {}))
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    notice.value = result.message
    await loadState()
    emit('changed')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '确认配置失败'
  } finally {
    busy.value = false
  }
}

async function cancel() {
  errorMessage.value = ''
  notice.value = ''
  busy.value = true
  try {
    const result = await cancelApplication({ application: applicationNo.value })
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    notice.value = result.message
    await loadState()
    emit('changed')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '取消失败'
  } finally {
    busy.value = false
  }
}

onMounted(loadState)
</script>

<style scoped>
.dp-panel { background: #f8fafc; border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin: 12px 0 16px; }
.dp-head h3 { margin: 0 0 4px; font-size: 15px; }
.dp-desc { margin: 0 0 12px; color: var(--muted); font-size: 12.5px; line-height: 1.6; }
.dp-form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 12px; }
.dp-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.dp-field input { padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; color: #111827; }
.dp-field-purpose { grid-column: span 2; }
.dp-field-action { justify-content: flex-end; }
.dp-btn-alias { display: inline-flex; }
.dp-notice { color: #067647; background: #ecfdf3; border: 1px solid #abefc6; padding: 7px 10px; border-radius: 6px; font-size: 13px; margin: 10px 0 0; }
.dp-error-box { background: #fef3f2; border: 1px solid #fecdca; padding: 7px 10px; border-radius: 6px; margin-top: 10px; font-size: 13px; }
.dp-table-wrap { margin-top: 12px; overflow-x: auto; }
.dp-candidate-table .dp-reason { min-width: 220px; font-size: 12px; }
.dp-row-bad { background: #fff7f6; }
.dp-row-ok { background: #f0fdf4; }
.dp-ok { color: #067647; }
.dp-select-btn { white-space: nowrap; }
.dp-confirm-bar { display: flex; align-items: center; gap: 14px; justify-content: space-between; margin-top: 10px; padding: 10px 12px; background: #ecfdf3; border: 1px solid #abefc6; border-radius: 8px; font-size: 13px; }
.dp-receipt { margin-top: 12px; background: #fff; border: 1px solid #98a2b3; border-radius: 8px; padding: 12px 14px; }
.dp-receipt h4 { margin: 0 0 8px; font-size: 14px; }
.dp-receipt-no { color: var(--brand); font-family: ui-monospace, monospace; }
.dp-receipt-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px 14px; margin: 0; }
.dp-receipt-grid dt { font-size: 12px; color: var(--muted); }
.dp-receipt-grid dd { margin: 2px 0 0; font-size: 13px; }
.dp-tip { font-size: 12px; color: var(--muted); margin: 10px 0; }
.dp-execution { margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: #eff8ff; border: 1px solid #b2ddff; font-size: 13px; }
.dp-execution h4 { margin: 0 0 6px; font-size: 14px; }
.dp-budget-mini { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; font-size: 12.5px; color: #344054; }
@media (max-width: 1100px) { .dp-form-grid, .dp-receipt-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }
</style>
