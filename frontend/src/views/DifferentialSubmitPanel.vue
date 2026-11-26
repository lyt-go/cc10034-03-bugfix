<template>
  <div data-testid="differential-panel">
    <div data-testid="query-submit-panel">
      <section class="dp-panel dsql-panel" data-testid="differential-submit-panel" data-panel="differential-submit" data-module="differential_sql">
        <header class="dp-head">
          <h3>差分查询提交 · 原申请执行许可</h3>
          <p class="dp-desc">
            提交原申请编号与实际使用参数；服务端复用同一份用途与费用校验，并按配置回执核对参数与获准版本。配置事后被停用不影响已签发回执。
          </p>
        </header>

        <div class="dsql-grid" data-testid="query-form">
          <label class="dp-field">
            <span>原申请编号</span>
            <input
              v-model="applicationNo"
              list="dsql-application-options"
              data-testid="query-application"
              aria-label="原申请编号"
              placeholder="GRAN-0004"
              @change="loadState"
            />
            <datalist id="dsql-application-options">
              <option v-for="app in applications" :key="app.application_no" :value="app.application_no">
                {{ app.dp_status }}｜额度 {{ app.额度Epsilon }}
              </option>
            </datalist>
          </label>
          <label class="dp-field">
            <span>查询用户</span>
            <input v-model="queryUser" data-testid="query-user" aria-label="查询用户" placeholder="数据分析-周倩" />
          </label>
          <label class="dp-field">
            <span>回执编号</span>
            <input v-model="receiptNo" data-testid="query-receipt" aria-label="回执编号" placeholder="确认配置后自动带入" />
          </label>
          <label class="dp-field dsql-field-wide">
            <span>查询语句</span>
            <input v-model="sql" data-testid="query-sql" aria-label="查询语句" placeholder="SELECT ... 差分聚合查询" />
          </label>
        </div>

        <details class="dsql-params" open>
          <summary>实际使用参数（按回执核对）</summary>
          <div class="dsql-grid">
            <label class="dp-field">
              <span>配置ID</span>
              <input v-model="configId" data-testid="query-config-id" aria-label="配置ID" inputmode="numeric" />
            </label>
            <label class="dp-field">
              <span>配置编号</span>
              <input v-model="configNo" data-testid="query-config-no" aria-label="配置编号" />
            </label>
            <label class="dp-field">
              <span>实际版本</span>
              <input v-model="configVersion" data-testid="query-config-version" aria-label="实际版本" />
            </label>
            <label class="dp-field">
              <span>申请字段</span>
              <input v-model="field" data-testid="query-field" aria-label="申请字段" />
            </label>
            <label class="dp-field">
              <span>实际费用ε</span>
              <input v-model="cost" data-testid="query-cost" aria-label="实际费用" inputmode="decimal" />
            </label>
          </div>
        </details>

        <div class="dsql-actions">
          <span class="dp-btn-alias" data-testid="submit-differential">
            <span class="dp-btn-alias" data-testid="execute-query">
              <button class="btn primary" type="button" data-testid="submit-execution" aria-label="提交执行" :disabled="busy" @click="submit">
                {{ busy ? '提交执行中…' : '提交执行差分查询' }}
              </button>
            </span>
          </span>
          <button class="btn ghost" type="button" data-testid="query-cancel-application" :disabled="busy" @click="cancel">
            取消申请（不消耗额度）
          </button>
          <button class="btn" type="button" data-testid="query-refresh" :disabled="busy" @click="loadState">刷新回执</button>
        </div>

        <p v-if="notice" class="dp-notice" data-testid="execute-result" role="status">
          <span data-testid="panel-notice">{{ notice }}</span>
        </p>
        <div v-if="errorMessage" class="dp-error-box" data-testid="execute-error" role="alert">
          <span class="error-text" data-testid="panel-error">{{ errorMessage }}</span>
        </div>

        <div v-if="execution" class="dp-execution" data-testid="query-execution-card">
          <h4>执行结果（同一笔申请 {{ execution.申请编号 || execution.application_no }}）</h4>
          <ul class="dsql-result-list">
            <li>查询编号：<strong data-testid="result-query-no">{{ execution.查询编号 || execution.query_no }}</strong></li>
            <li>执行状态：<strong data-testid="result-status">{{ execution.执行状态 || execution.execution_status }}</strong></li>
            <li>获准版本：<strong data-testid="result-approved-version">{{ execution.获准版本 || execution.approved_version }}</strong></li>
            <li>消耗 Epsilon：<strong data-testid="result-cost">{{ execution.消耗Epsilon }}</strong></li>
            <li>预算剩余：<strong data-testid="result-remaining">{{ execution.预算剩余Epsilon || execution.remaining }}</strong></li>
            <li v-if="execution.deactivated_at_execution">
              配置提交后已被停用（执行时状态：{{ execution.执行时配置状态 }}），仍按回执锁定的获准版本执行
            </li>
          </ul>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  cancelApplication,
  executeDifferential,
  fetchDpState,
  type DpState,
} from '@/domain/dpFlow'

const emit = defineEmits<{ changed: [] }>()

const applicationNo = ref('GRAN-0004')
const queryUser = ref('数据分析-周倩')
const receiptNo = ref('')
const sql = ref('')
const configId = ref<string>('3')
const configNo = ref('NOIS-0003')
const configVersion = ref('v2.0')
const field = ref('频次统计')
const cost = ref('0.1')

const state = ref<DpState | null>(null)
const busy = ref(false)
const notice = ref('')
const errorMessage = ref('')

const applications = computed(() => state.value?.applications ?? [])
const execution = computed(() => state.value?.execution ?? null)

function hydrate(data: DpState) {
  state.value = data
  if (data.application) {
    applicationNo.value = data.application.application_no
  }
  const receipt = data.receipt
  if (receipt) {
    receiptNo.value = receipt.receipt_no
    configId.value = String(receipt.config_id ?? '')
    configNo.value = String(receipt.配置编号 ?? receipt.config_no ?? '')
    configVersion.value = String(receipt.获准版本 ?? receipt.config_version ?? '')
    field.value = String(receipt.申请字段 ?? receipt.field ?? field.value)
    cost.value = String(receipt.cost ?? cost.value)
  }
  if (data.execution) {
    notice.value = `申请 ${applicationNo.value} 已执行：${data.execution.查询编号 ?? data.execution.query_no}，可刷新隐私预算页核对余额`
  }
}

async function loadState() {
  errorMessage.value = ''
  try {
    hydrate(await fetchDpState(applicationNo.value))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回执状态读取失败'
  }
}

async function submit() {
  busy.value = true
  errorMessage.value = ''
  notice.value = ''
  try {
    const result = await executeDifferential({
      application: applicationNo.value,
      application_no: applicationNo.value,
      receipt_no: receiptNo.value || undefined,
      sql: sql.value || undefined,
      user: queryUser.value || undefined,
      config_id: configId.value || undefined,
      config_no: configNo.value || undefined,
      config_version: configVersion.value || undefined,
      field: field.value || undefined,
      cost: cost.value || undefined,
    })
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    notice.value = result.message
    if (result.execution) {
      hydrate({ ...(state.value as DpState), execution: result.execution } as DpState)
    }
    await loadState()
    // loadState/hydrate 会用通用提示覆盖，这里恢复包含获准版本/停用冲突说明的服务端结论。
    notice.value = result.message
    emit('changed')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '差分查询提交失败'
  } finally {
    busy.value = false
  }
}

async function cancel() {
  busy.value = true
  errorMessage.value = ''
  notice.value = ''
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
.dsql-panel { border-color: #b2ddff; background: #f5faff; }
.dp-head h3 { margin: 0 0 4px; font-size: 15px; }
.dp-desc { margin: 0 0 12px; color: var(--muted); font-size: 12.5px; line-height: 1.6; }
.dsql-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 12px; }
.dp-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.dp-field input { padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; color: #111827; }
.dsql-field-wide { grid-column: span 2; }
.dsql-params { margin-top: 10px; font-size: 12.5px; }
.dsql-params summary { cursor: pointer; color: #344054; margin-bottom: 8px; }
.dsql-actions { display: flex; gap: 10px; align-items: center; margin-top: 14px; }
.dp-btn-alias { display: inline-flex; }
.dp-notice { color: #067647; background: #ecfdf3; border: 1px solid #abefc6; padding: 8px 10px; border-radius: 6px; font-size: 13px; margin: 12px 0 0; }
.dp-error-box { background: #fef3f2; border: 1px solid #fecdca; padding: 8px 10px; border-radius: 6px; margin-top: 12px; font-size: 13px; }
.dp-execution { margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: #fff; border: 1px solid #abefc6; font-size: 13px; }
.dp-execution h4 { margin: 0 0 6px; font-size: 14px; }
.dsql-result-list { margin: 0; padding-left: 18px; display: grid; gap: 4px; }
@media (max-width: 1100px) { .dsql-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }
</style>
