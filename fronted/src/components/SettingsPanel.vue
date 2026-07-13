<template>
  <Teleport to="body" :disabled="embedded">
    <Transition name="modal">
      <div v-if="visible || embedded" :class="['settings-overlay', { 'is-embedded': embedded }]" @click.self="close">
        <div :class="['settings-panel', { 'settings-panel-wide': ['memory', 'agent_params', 'monitor', 'avatar'].includes(activeTab), 'is-embedded': embedded }]">
          <div class="settings-header">
            <div class="console-brand">
              <span class="brand-mark" aria-hidden="true"></span>
              <div><span>FEINA LIVE</span><h2>运营控制台</h2></div>
            </div>
            <div class="header-meta">
              <button
                v-if="embedded"
                class="theme-toggle"
                type="button"
                :aria-pressed="isLight"
                :aria-label="isLight ? '切换到暗色主题' : '切换到亮色主题'"
                :title="isLight ? '切换到暗色主题' : '切换到亮色主题'"
                @click="toggleTheme"
              >
                <svg v-if="isLight" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 15.2A8 8 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
                <svg v-else viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
                <span>{{ isLight ? '暗色' : '亮色' }}</span>
              </button>
              <span :class="['connection-pill', connected ? 'online' : 'offline']">{{ connected ? '后端已连接' : '后端未连接' }}</span>
              <button v-if="!embedded" class="close-btn" aria-label="关闭控制台" @click="close">&times;</button>
            </div>
          </div>

          <!-- ===== 连接状态 ===== -->
          <div v-if="!connected" class="settings-content connect-state">
            <div v-if="connecting" class="connect-box">
              <div class="spinner"></div>
              <p>正在连接后端...</p>
            </div>
            <div v-else class="connect-box connect-error">
              <div class="err-icon">!</div>
              <p>无法连接到后端</p>
              <p class="hint">请确认后端服务已启动</p>
              <button class="btn btn-primary" @click="loadConfig">重新连接</button>
            </div>
          </div>

          <!-- ===== 配置表单（仅连接成功后显示） ===== -->
          <template v-else>
            <label class="mobile-tab-picker">
              <span>当前分区</span>
              <select v-model="activeTab" aria-label="选择控制台分区">
                <option v-for="tab in tabs" :key="`mobile-${tab.key}`" :value="tab.key">{{ tab.label }}</option>
              </select>
            </label>
            <nav class="settings-tabs" aria-label="控制台主导航">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                :class="['tab-btn', { active: activeTab === tab.key }]"
                :aria-current="activeTab === tab.key ? 'page' : undefined"
                @click="activeTab = tab.key"
              >
                <span class="tab-indicator" aria-hidden="true"></span>
                {{ tab.label }}
              </button>
            </nav>

            <div :class="['settings-content', { 'settings-content-memory': activeTab === 'memory' }]">
              <!-- Tab: 总览 -->
              <div v-if="activeTab === 'overview'" class="tab-content overview-content">
                <div class="overview-heading">
                  <div><span class="eyebrow">SYSTEM OVERVIEW</span><h1>直播运行总览</h1><p>集中查看关键服务，并执行不会改变持久配置的运行时操作。</p></div>
                  <div class="overview-actions">
                    <span class="last-updated">更新于 {{ runtimeUpdatedAt || '—' }}</span>
                    <button class="btn btn-secondary" :disabled="runtimeBusy === 'refresh'" @click="refreshOverview">{{ runtimeBusy === 'refresh' ? '刷新中…' : '刷新状态' }}</button>
                    <button class="btn btn-primary" @click="openLiveDisplay">打开直播画面</button>
                  </div>
                </div>

                <div class="runtime-grid">
                  <article class="runtime-card">
                    <div class="runtime-card-head"><span :class="['runtime-dot', runtimeHealth.status === 'healthy' ? 'ok' : 'bad']"></span><span>后端</span></div>
                    <strong>{{ runtimeHealth.status === 'healthy' ? '服务正常' : '需要检查' }}</strong>
                    <p>消息队列 {{ runtimeHealth.message_queue?.size ?? 0 }} 条 · {{ runtimeHealth.components?.message_queue || '未知' }}</p>
                  </article>
                  <article class="runtime-card">
                    <div class="runtime-card-head"><span :class="['runtime-dot', liveState.running ? 'ok' : 'idle']"></span><span>直播平台</span></div>
                    <strong>{{ liveState.running ? liveState.platform : '未启动' }}</strong>
                    <p>同一时刻只绑定一个标准化直播会话</p>
                  </article>
                  <article class="runtime-card">
                    <div class="runtime-card-head"><span :class="['runtime-dot', agentRuntime.running ? 'ok' : 'idle']"></span><span>Agent</span></div>
                    <strong>{{ agentRuntime.running ? '运行中' : agentRuntime.runtime_status || '已停止' }}</strong>
                    <p>{{ agentRuntime.configured_scenario_id || '未绑定场景' }} · 待处理 {{ agentRuntime.events?.pending ?? 0 }}</p>
                    <button class="card-action" :disabled="runtimeBusy === 'agent'" @click="toggleAgent">{{ agentRuntime.running ? '停止 Agent' : '启动 Agent' }}</button>
                  </article>
                  <article class="runtime-card">
                    <div class="runtime-card-head"><span :class="['runtime-dot', avatarRuntimeState.state === 'running' ? 'ok' : avatarRuntimeState.state === 'failed' ? 'bad' : 'idle']"></span><span>FeinaAvatar</span></div>
                    <strong>{{ avatarStatusText }}</strong>
                    <p>{{ avatarRuntimeState.error || 'Spout2 正式输出与控制台预览' }}</p>
                    <button class="card-action" :disabled="runtimeBusy === 'avatar'" @click="toggleAvatar">{{ avatarRuntimeState.state === 'running' ? '停止渲染' : '启动渲染' }}</button>
                  </article>
                  <article class="runtime-card">
                    <div class="runtime-card-head"><span :class="['runtime-dot', aiRuntime.playback?.owner_id ? 'ok' : 'idle']"></span><span>主播消费链路</span></div>
                    <strong>{{ aiRuntime.unanswered_count ?? 0 }} 条待回复</strong>
                    <p>缓冲 {{ aiRuntime.buffer_size ?? 0 }} · 播放端 {{ aiRuntime.playback?.ready_clients ?? 0 }}</p>
                  </article>
                  <article class="runtime-card">
                    <div class="runtime-card-head"><span :class="['runtime-dot', musicState.current ? 'ok' : 'idle']"></span><span>音乐系统</span></div>
                    <strong>{{ musicState.current?.track.title || '等待点歌' }}</strong>
                    <p>队列 {{ musicState.queue.length }} 首 · 音量 {{ Math.round(musicState.volume * 100) }}%</p>
                    <div class="card-actions"><button class="card-action" @click="musicStore.togglePlay">{{ musicState.paused ? '继续' : '暂停' }}</button><button class="card-action" :disabled="!musicState.current" @click="() => musicStore.skipCurrent()">切歌</button></div>
                  </article>
                </div>
              </div>

              <!-- Tab: AI主播 -->
              <div v-if="activeTab === 'host'" class="tab-content">
                <div class="section-title">主播回复参数</div>
                <div class="form-group">
                  <label>回复间隔 <span class="hint">(秒, 1-60)</span></label>
                  <input type="number" v-model.number="cfg.host.reply_interval" min="1" max="60" />
                </div>
                <div class="form-group">
                  <label>最大回复长度 <span class="hint">(字, 50-500)</span></label>
                  <input type="number" v-model.number="cfg.host.max_reply_length" min="50" max="500" />
                </div>
                <div class="form-group">
                  <label class="checkbox-label">
                    <input type="checkbox" v-model="cfg.host.disable_thinking" />
                    禁用思考链 <span class="hint">(模型不支持时取消勾选)</span>
                  </label>
                </div>
              </div>

              <!-- Tab: AI模型 -->
              <div v-if="activeTab === 'ai_models'" class="tab-content">
                <div class="section-title">通用模型</div>
                <p class="section-desc">音乐验证、上下文总结、RAG 检索等任务</p>
                <div class="form-group">
                  <label>API URL</label>
                  <input type="text" v-model="cfg.llm.api_url" placeholder="https://api.example.com/v1" />
                </div>
                <div class="form-group">
                  <label>API Key <span v-if="cfg.llm.api_key.includes(MASKED)" class="hint">(已隐藏)</span></label>
                  <input :type="cfg.llm.api_key.includes(MASKED) ? 'password' : 'text'" v-model="cfg.llm.api_key" />
                </div>
                <div class="form-group">
                  <label>模型名</label>
                  <input type="text" v-model="cfg.llm.model" placeholder="gpt-4o" />
                </div>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>温度 <span class="range-value">{{ cfg.llm.temperature }}</span></label>
                    <input type="range" v-model.number="cfg.llm.temperature" min="0" max="1" step="0.05" />
                  </div>
                  <div class="form-group">
                    <label>Top P <span class="range-value">{{ cfg.llm.top_p }}</span></label>
                    <input type="range" v-model.number="cfg.llm.top_p" min="0" max="1" step="0.1" />
                  </div>
                </div>
                <div class="form-group">
                  <label>最大 Token 数</label>
                  <input type="number" v-model.number="cfg.llm.max_tokens" min="50" max="8192" />
                </div>
                <div class="form-group">
                  <label class="checkbox-label">
                    <input type="checkbox" v-model="cfg.llm.disable_thinking" />
                    禁用思考链 <span class="hint">(模型不支持时取消勾选)</span>
                  </label>
                </div>

                <div class="section-title">主播模型</div>
                <p class="section-desc">AI 主播对话、弹幕回复、风格化解说 (HostRuntime)</p>
                <div class="form-group">
                  <label>API URL</label>
                  <input type="text" v-model="cfg.host.api_url" placeholder="留空则使用通用模型 API URL" />
                </div>
                <div class="form-group">
                  <label>API Key <span v-if="cfg.host.api_key.includes(MASKED)" class="hint">(已隐藏)</span></label>
                  <input :type="cfg.host.api_key.includes(MASKED) ? 'password' : 'text'" v-model="cfg.host.api_key" placeholder="留空则使用通用模型 API Key" />
                </div>
                <div class="form-group">
                  <label>模型名</label>
                  <input type="text" v-model="cfg.host.model" placeholder="deepseek-v4-flash" />
                </div>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>温度 <span class="range-value">{{ cfg.host.temperature }}</span></label>
                    <input type="range" v-model.number="cfg.host.temperature" min="0" max="1" step="0.1" />
                  </div>
                  <div class="form-group">
                    <label>Top P <span class="range-value">{{ cfg.host.top_p }}</span></label>
                    <input type="range" v-model.number="cfg.host.top_p" min="0" max="1" step="0.1" />
                  </div>
                </div>
                <div class="form-group">
                  <label>最大 Token 数</label>
                  <input type="number" v-model.number="cfg.host.max_tokens" min="50" max="4096" />
                </div>

                <div class="section-title">Agent 模型</div>
                <p class="section-desc">通用 Agent 的决策与解说编排模型 <span class="hint">启停请在主界面使用 AI ON/OFF 按钮</span></p>
                <div class="form-group">
                  <label>API URL</label>
                  <input type="text" v-model="cfg.agent.api_url" placeholder="https://api.example.com/v1" />
                </div>
                <div class="form-group">
                  <label>API Key <span v-if="cfg.agent.api_key.includes(MASKED)" class="hint">(已隐藏)</span></label>
                  <input :type="cfg.agent.api_key.includes(MASKED) ? 'password' : 'text'" v-model="cfg.agent.api_key" />
                </div>
                <div class="form-group">
                  <label>模型名</label>
                  <input type="text" v-model="cfg.agent.model" placeholder="deepseek-v4-flash" />
                </div>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>温度 <span class="range-value">{{ cfg.agent.temperature }}</span></label>
                    <input type="range" v-model.number="cfg.agent.temperature" min="0" max="1" step="0.1" />
                  </div>
                  <div class="form-group">
                    <label>最大 Token 数</label>
                    <input type="number" v-model.number="cfg.agent.max_tokens" min="50" max="16384" />
                  </div>
                </div>
                <div class="form-group">
                  <label class="checkbox-label">
                    <input type="checkbox" v-model="cfg.agent.disable_thinking" />
                    禁用思考链 <span class="hint">(模型不支持时取消勾选)</span>
                  </label>
                </div>
                <div class="section-title">向量模型 (Embedding)</div>
                <p class="section-desc">用于记忆语义检索，未配置时自动退化到纯关键词检索</p>
                <div class="form-group">
                  <label>模型网关</label>
                  <input value="Bifrost Gateway (OpenAI-compatible)" disabled />
                </div>
                <div class="form-group">
                  <label>模型名</label>
                  <input type="text" v-model="cfg.embedding.model" placeholder="text-embedding-3-small" />
                </div>
                <div class="form-group">
                  <label>API URL <span class="hint">(留空则使用通用模型 API URL)</span></label>
                  <input type="text" v-model="cfg.embedding.api_url" placeholder="https://api.example.com/v1" />
                </div>
                <div class="form-group">
                  <label>API Key <span v-if="cfg.embedding.api_key.includes(MASKED)" class="hint">(已隐藏)</span></label>
                  <input :type="cfg.embedding.api_key.includes(MASKED) ? 'password' : 'text'" v-model="cfg.embedding.api_key" placeholder="留空则使用通用模型 API Key" />
                </div>
                <div class="form-group">
                  <label>向量维度 <span class="hint">(留空自动)</span></label>
                  <input type="number" v-model.number="cfg.embedding.dimensions" placeholder="1536" />
                </div>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>用户知识图使用 Embedding</label>
                    <select v-model="cfg.embedding.user_graph_enabled">
                      <option :value="true">启用</option>
                      <option :value="false">关闭（关键词兜底）</option>
                    </select>
                  </div>
                  <div class="form-group">
                    <label>游戏知识图使用 Embedding</label>
                    <select v-model="cfg.embedding.game_graph_enabled">
                      <option :value="true">启用</option>
                      <option :value="false">关闭（关键词兜底）</option>
                    </select>
                  </div>
                </div>
              </div>

              <!-- Tab: 语音 -->
              <div v-if="activeTab === 'tts'" class="tab-content">
                <div class="section-title">Speech Gateway</div>
                <p class="section-desc">供应商凭据、路由和 fallback 在独立 Gateway 中管理；控制台只配置统一语音接口。</p>
                <div class="form-group">
                  <label>Gateway URL</label>
                  <input type="text" v-model="cfg.tts.gateway_url" placeholder="http://127.0.0.1:8091/v1" />
                </div>
                <div class="form-group">
                  <label>Gateway API Key <span v-if="cfg.tts.api_key.includes(MASKED)" class="hint">(已隐藏)</span></label>
                  <input :type="cfg.tts.api_key.includes(MASKED) ? 'password' : 'text'" v-model="cfg.tts.api_key" placeholder="本地无鉴权时留空" />
                </div>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>TTS 提供者</label>
                    <select v-model="selectedSpeechProvider" @change="selectSpeechProvider(true)">
                      <option v-for="(provider, name) in speechGatewayConfig.providers" :key="name" :value="name">
                        {{ speechSchemaByType(provider.type)?.label || provider.type }} · {{ name }}
                      </option>
                    </select>
                  </div>
                  <div class="form-group">
                    <label>备用提供者（按选择顺序）</label>
                    <select multiple v-model="speechFallbackProviders">
                      <option v-for="name in fallbackSpeechProviders" :key="name" :value="name">{{ name }}</option>
                    </select>
                  </div>
                </div>
                <div v-if="activeSpeechSchema" class="settings-subcard">
                  <div class="section-title">{{ activeSpeechSchema.label }} 配置</div>
                  <div v-for="field in activeSpeechSchema.fields" :key="field.key" class="form-group">
                    <label>{{ field.label }} <span v-if="field.required" class="hint">(必填)</span></label>
                    <input
                      v-if="field.type === 'text' || field.type === 'url' || field.type === 'secret'"
                      :type="field.type === 'secret' && String(speechProviderDraft[field.key] || '').includes(MASKED) ? 'password' : 'text'"
                      v-model="speechProviderDraft[field.key]"
                      :placeholder="field.placeholder || ''"
                    />
                    <input
                      v-else-if="field.type === 'number'"
                      type="number"
                      v-model.number="speechProviderDraft[field.key]"
                      :min="field.min"
                      :max="field.max"
                    />
                    <label v-else-if="field.type === 'boolean'" class="checkbox-label">
                      <input type="checkbox" v-model="speechProviderDraft[field.key]" /> 启用
                    </label>
                    <select v-else-if="field.type === 'multiselect'" multiple v-model="speechProviderDraft[field.key]">
                      <option v-for="option in field.options || []" :key="option" :value="option">{{ option }}</option>
                    </select>
                  </div>
                  <div class="card-actions">
                    <button class="action-btn" :disabled="speechGatewayBusy" @click="saveSpeechProvider">
                      {{ speechGatewayBusy ? '保存中…' : '保存提供者配置' }}
                    </button>
                    <button class="action-btn" :disabled="speechGatewayBusy" @click="probeSpeechProvider">主动探测</button>
                  </div>
                </div>
                <p v-if="speechGatewayError" class="status-error">{{ speechGatewayError }}</p>
                <p v-else-if="selectedSpeechStatus" class="section-desc">
                  状态：{{ selectedSpeechStatus.configured ? '已配置' : '未配置' }} · 熔断器 {{ selectedSpeechStatus.circuit || '未知' }} ·
                  成功率 {{ selectedSpeechStatus.metrics?.success_rate ?? '暂无数据' }} · RTF P95 {{ selectedSpeechStatus.metrics?.rtf?.p95 ?? '暂无数据' }}
                </p>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>编码格式</label>
                    <select v-model="cfg.tts.response_format">
                      <option value="mp3">MP3</option>
                      <option value="wav">WAV</option>
                      <option value="pcm">PCM</option>
                      <option value="ogg_opus">Ogg Opus</option>
                    </select>
                  </div>
                  <div class="form-group">
                    <label>语速 <span class="range-value">{{ cfg.tts.speed }}</span></label>
                    <input type="range" v-model.number="cfg.tts.speed" min="0.5" max="2.0" step="0.1" />
                  </div>
                </div>
                <div class="form-group">
                  <label>合成超时（秒）</label>
                  <input type="number" v-model.number="cfg.tts.timeout_seconds" min="1" max="300" />
                </div>
              </div>

              <!-- Tab: 消息调度 -->
              <div v-if="activeTab === 'messaging'" class="tab-content">
                <div class="section-title">弹幕优先级</div>
                <table class="compact-table">
                  <tbody>
                  <tr><td><label>饥饿时间窗口 <span class="hint">(秒)</span></label></td><td><input type="number" v-model.number="cfg.messaging.danmaku_starvation_seconds" min="5" max="300" /></td></tr>
                  <tr><td><label>洪流阈值 <span class="hint">(条)</span></label></td><td><input type="number" v-model.number="cfg.messaging.danmaku_flood_threshold" min="1" max="50" /></td></tr>
                  <tr><td><label>洪流窗口 <span class="hint">(秒)</span></label></td><td><input type="number" v-model.number="cfg.messaging.danmaku_flood_window" min="5" max="120" /></td></tr>
                  </tbody>
                </table>

                <div class="section-title">礼物优先级</div>
                <table class="compact-table">
                  <tbody>
                  <tr><td><label>饥饿时间 <span class="hint">(秒)</span></label></td><td><input type="number" v-model.number="cfg.messaging.gift_starvation_seconds" min="10" max="600" /></td></tr>
                  <tr><td><label>洪流阈值 <span class="hint">(条)</span></label></td><td><input type="number" v-model.number="cfg.messaging.gift_flood_threshold" min="1" max="20" /></td></tr>
                  <tr><td><label>洪流窗口 <span class="hint">(秒)</span></label></td><td><input type="number" v-model.number="cfg.messaging.gift_flood_window" min="10" max="180" /></td></tr>
                  <tr><td><label>最高档价值 <span class="hint">(人民币分，100=1元)</span></label></td><td><input type="number" v-model.number="cfg.messaging.gift_value_highest" min="100" /></td></tr>
                  <tr><td><label>高档价值</label></td><td><input type="number" v-model.number="cfg.messaging.gift_value_high" min="100" /></td></tr>
                  <tr><td><label>普通档价值</label></td><td><input type="number" v-model.number="cfg.messaging.gift_value_normal" min="10" /></td></tr>
                  <tr><td><label>低档价值</label></td><td><input type="number" v-model.number="cfg.messaging.gift_value_low" min="1" /></td></tr>
                  </tbody>
                </table>

                <div class="section-title">队列</div>
                <table class="compact-table">
                  <tbody>
                  <tr><td><label>用户冷却 <span class="hint">(秒)</span></label></td><td><input type="number" v-model.number="cfg.messaging.user_cooldown_seconds" min="0" max="60" step="0.1" /></td></tr>
                  <tr><td><label>消息 TTL <span class="hint">(秒)</span></label></td><td><input type="number" v-model.number="cfg.messaging.default_ttl_seconds" min="5" max="300" /></td></tr>
                  </tbody>
                </table>

                <div class="section-title">频率限制 <span class="hint">(最小间隔秒)</span></div>
                <table class="compact-table">
                  <tbody>
                  <tr><td><label>解说请求</label></td><td><input type="number" v-model.number="cfg.messaging.rate_limit_commentary" min="0" max="60" /></td></tr>
                  <tr><td><label>弹幕回复</label></td><td><input type="number" v-model.number="cfg.messaging.rate_limit_danmaku" min="0" max="30" /></td></tr>
                  <tr><td><label>礼物感谢</label></td><td><input type="number" v-model.number="cfg.messaging.rate_limit_gift" min="0" max="60" /></td></tr>
                  </tbody>
                </table>
              </div>

              <!-- Tab: 数字人 -->
              <div v-if="activeTab === 'avatar'" class="tab-content">
                <div class="form-group">
                  <label class="checkbox-label"><input type="checkbox" v-model="cfg.avatar.enabled" /> 启用 FeinaAvatar</label>
                </div>
                <div class="form-group">
                  <label>角色</label>
                  <div class="input-row">
                    <select v-model="cfg.avatar.character" class="flex-select">
                      <option v-for="char in characters" :key="char.name" :value="char.name">{{ char.name }}</option>
                    </select>
                    <button class="small-btn" @click="openImagesFolder">打开图片文件夹</button>
                  </div>
                </div>
                <div v-if="cfg.avatar.outputs.preview.enabled" class="avatar-preview">
                  <img :src="avatarPreviewUrl" alt="FeinaAvatar preview" />
                  <span>{{ avatarStatusText }}</span>
                </div>
                <div class="section-title">动作与口型</div>
                <div class="form-row-2">
                  <div class="form-group"><label>默认动作</label><select v-model="cfg.avatar.motion.source"><option value="autonomous">自主漫步</option><option value="browser">浏览器鼠标</option></select></div>
                  <div class="form-group"><label>口型源</label><select v-model="cfg.avatar.lip_sync.source"><option value="browser_audio">真实播放音频</option><option value="disabled">关闭</option></select></div>
                  <div class="form-group"><label class="checkbox-label"><input type="checkbox" v-model="cfg.avatar.motion.allow_browser_control" /> 允许管理指令切换鼠标追踪</label></div>
                  <div class="form-group"><label>口型灵敏度</label><input type="number" v-model.number="cfg.avatar.lip_sync.sensitivity" min="0.1" max="10" step="0.1" /></div>
                  <div class="form-group"><label>噪声门</label><input type="number" v-model.number="cfg.avatar.lip_sync.noise_gate" min="0" max="0.5" step="0.005" /></div>
                  <div class="form-group"><label>张嘴响应(ms)</label><input type="number" v-model.number="cfg.avatar.lip_sync.attack_ms" min="1" max="1000" /></div>
                  <div class="form-group"><label>闭嘴响应(ms)</label><input type="number" v-model.number="cfg.avatar.lip_sync.release_ms" min="1" max="2000" /></div>
                </div>
                <div class="section-title">渲染器 <span class="hint">(修改后重启生效)</span></div>
                <div class="form-row-2">
                  <div class="form-group"><label>模型</label><select v-model="cfg.avatar.renderer.model"><option value="tha3">THA3</option><option value="tha4">THA4</option><option value="tha4_student">THA4 Student</option></select></div>
                  <div class="form-group"><label>后端</label><select v-model="cfg.avatar.renderer.backend"><option value="onnxruntime">ONNX Runtime</option><option value="tensorrt">TensorRT</option></select></div>
                  <div class="form-group"><label>精度</label><select v-model="cfg.avatar.renderer.precision"><option value="fp32">FP32</option><option value="fp16">FP16</option></select></div>
                  <div class="form-group"><label>帧率</label><select v-model.number="cfg.avatar.renderer.frame_rate"><option :value="20">20</option><option :value="30">30</option><option :value="60">60</option></select></div>
                  <div class="form-group"><label>插帧</label><select v-model.number="cfg.avatar.renderer.interpolation"><option :value="1">关</option><option :value="2">2x</option><option :value="4">4x</option></select></div>
                  <div class="form-group"><label>超分</label><select v-model.number="cfg.avatar.renderer.super_resolution"><option :value="1">关</option><option :value="2">2x</option><option :value="4">4x</option></select></div>
                  <div class="form-group"><label>RAM 缓存(MB)</label><input type="number" v-model.number="cfg.avatar.renderer.ram_cache_mb" min="0" /></div>
                  <div class="form-group"><label>VRAM 缓存(MB)</label><input type="number" v-model.number="cfg.avatar.renderer.vram_cache_mb" min="0" /></div>
                  <label class="checkbox-label"><input type="checkbox" v-model="cfg.avatar.renderer.separable" /> 可分离卷积</label>
                  <label class="checkbox-label"><input type="checkbox" v-model="cfg.avatar.renderer.use_eyebrow" /> 眉毛参数</label>
                </div>
                <div class="section-title">输出</div>
                <div class="form-row-2">
                  <div class="form-group"><label class="checkbox-label"><input type="checkbox" v-model="cfg.avatar.outputs.spout.enabled" /> Spout2 正式输出</label></div>
                  <div class="form-group"><label>Spout 名称</label><input type="text" v-model="cfg.avatar.outputs.spout.name" /></div>
                  <div class="form-group"><label class="checkbox-label"><input type="checkbox" v-model="cfg.avatar.outputs.preview.enabled" /> 控制面板预览</label></div>
                  <div class="form-group"><label>预览帧率</label><input type="number" v-model.number="cfg.avatar.outputs.preview.frame_rate" min="1" max="30" /></div>
                  <div class="form-group"><label>预览质量</label><input type="number" v-model.number="cfg.avatar.outputs.preview.quality" min="20" max="100" /></div>
                </div>
              </div>

              <!-- Tab: Agent 参数 -->
              <div v-if="activeTab === 'agent_params'" class="tab-content">
                <AgentSettingsPanel v-model="cfg.agent" />
              </div>

              <!-- Tab: 音乐 -->
              <div v-if="activeTab === 'music'" class="tab-content">
                <MusicManagementPanel />
                <div class="section-title">音乐 Provider</div>
                <p class="section-desc">音乐系统独立运行；Provider 和审核参数重启后生效。</p>
                <div class="form-group">
                  <label>默认 Provider</label>
                  <select v-model="cfg.music.default_provider">
                    <option value="auto">聚合所有可用源</option>
                    <option value="bilibili">Bilibili</option>
                    <option value="local">本地音乐</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>本地音乐目录 <span class="hint">(每行一个，重启后生效)</span></label>
                  <textarea
                    class="textarea-field"
                    rows="4"
                    :value="cfg.music.local_directories.join('\n')"
                    @input="setLocalDirectories"
                    placeholder="D:/Music"
                  ></textarea>
                </div>
                <div class="section-title">点歌策略</div>
                <div class="form-row-2">
                  <div class="form-group"><label>最短时长（秒）</label><input type="number" v-model.number="cfg.music.min_duration_seconds" min="1" /></div>
                  <div class="form-group"><label>最长时长（秒）</label><input type="number" v-model.number="cfg.music.max_duration_seconds" min="1" /></div>
                  <div class="form-group"><label>队列容量</label><input type="number" v-model.number="cfg.music.queue_capacity" min="1" max="100" /></div>
                  <div class="form-group"><label>每用户上限</label><input type="number" v-model.number="cfg.music.per_user_limit" min="1" max="20" /></div>
                  <div class="form-group"><label>搜索候选数</label><input type="number" v-model.number="cfg.music.search_candidates" min="1" max="20" /></div>
                  <div class="form-group">
                    <label class="checkbox-label"><input type="checkbox" v-model="cfg.music.allow_bare_bv" /> 允许裸 BV 触发点歌</label>
                  </div>
                </div>
                <div class="section-title">分层审核</div>
                <div class="form-row-2">
                  <div class="form-group"><label>规则接受阈值</label><input type="number" v-model.number="cfg.music.accept_score" min="0" max="100" /></div>
                  <div class="form-group"><label>规则拒绝阈值</label><input type="number" v-model.number="cfg.music.reject_score" min="-100" max="0" /></div>
                  <div class="form-group"><label>LLM 最低置信度</label><input type="number" v-model.number="cfg.music.llm_min_confidence" min="0" max="1" step="0.05" /></div>
                  <div class="form-group"><label>主播说话压低比例</label><input type="number" v-model.number="cfg.music.ducking_factor" min="0" max="1" step="0.05" /></div>
                  <div class="form-group"><label class="checkbox-label"><input type="checkbox" v-model="cfg.music.ducking_enabled" /> 默认启用自动压低</label></div>
                </div>
              </div>

              <!-- Tab: 直播 -->
              <div v-if="activeTab === 'live'" class="tab-content">
                <div class="section-title">直播平台 <span class="hint">(修改后重启生效)</span></div>
                <div class="form-group">
                  <label>当前平台</label>
                  <select v-model="cfg.live.platform">
                    <option value="bilibili">Bilibili</option>
                    <option value="douyin">抖音</option>
                    <option value="test">测试平台</option>
                  </select>
                </div>
                <template v-if="cfg.live.platform === 'bilibili'">
                  <div class="section-title">Bilibili</div>
                  <div class="form-row-2">
                    <div class="form-group"><label>直播间 ID</label><input type="number" v-model.number="cfg.bilibili.room_id" /></div>
                    <div class="form-group"><label>登录 UID</label><input type="number" v-model.number="cfg.bilibili.uid" placeholder="留空则不登录" /></div>
                  </div>
                  <div class="form-group"><label>SESSDATA <span v-if="cfg.bilibili.sessdata.includes(MASKED)" class="hint">(隐藏)</span></label>
                    <input :type="cfg.bilibili.sessdata.includes(MASKED) ? 'password' : 'text'" v-model="cfg.bilibili.sessdata" /></div>
                </template>
                <template v-else-if="cfg.live.platform === 'douyin'">
                  <div class="section-title">抖音</div>
                  <div class="form-group"><label>Web RID <span class="hint">(live.douyin.com/ 后的部分)</span></label><input type="text" v-model.trim="cfg.douyin.web_rid" /></div>
                  <div class="form-group"><label>Cookie <span v-if="cfg.douyin.cookie.includes(MASKED)" class="hint">(隐藏)</span></label>
                    <input :type="cfg.douyin.cookie.includes(MASKED) ? 'password' : 'text'" v-model="cfg.douyin.cookie" /></div>
                </template>
                <template v-else>
                  <div class="section-title">测试平台</div>
                  <p class="section-desc">由项目内部模拟标准弹幕、礼物和直播事件，不需要房间或平台凭据。修改后需重启。</p>
                </template>
                <div class="connection-check">
                  <button type="button" class="small-btn" :disabled="credentialChecking || cfg.live.platform === 'test'" @click="verifyPlatformCredentials">
                    {{ credentialChecking ? '验证中…' : '验证平台连接' }}
                  </button>
                  <span v-if="credentialStatus" :class="['credential-status', credentialStatus.valid ? 'ok' : 'bad']">{{ credentialStatus.message }}</span>
                </div>
                <div class="section-title">平台管理员身份</div>
                <div class="form-row-2">
                  <div class="form-group"><label>Bilibili UID</label><input type="text" v-model.trim="cfg.admin.identities.bilibili" /></div>
                  <div class="form-group"><label>抖音用户 ID / sec_uid</label><input type="text" v-model.trim="cfg.admin.identities.douyin" /></div>
                  <div class="form-group"><label>测试平台用户 ID</label><input type="text" v-model.trim="cfg.admin.identities.test" /></div>
                </div>
                <div class="section-title">管理员</div>
                <div class="form-group"><label>用户名兜底</label><input type="text" v-model="cfg.admin.username" /></div>
                <div class="section-title">公告</div>
                <div class="form-group"><textarea v-model="cfg.announcement" rows="3" class="textarea-field" /></div>
                <div class="section-title">数据存储</div>
                <div class="form-group"><label>SQLite <span class="hint">(重启后生效)</span></label><input type="text" v-model="cfg.storage.sqlite_path" /></div>
                <div class="form-group"><label>ChromaDB 目录 <span class="hint">(重启后生效)</span></label><input type="text" v-model="cfg.storage.chroma_path" /></div>
                <div class="form-group"><label>向量集合</label><input type="text" v-model="cfg.storage.chroma_collection" /></div>
                <p class="section-desc">ChromaDB：{{ vectorStatus.available ? '可用' : '不可用' }} · {{ vectorStatus.vector_count }} 条向量</p>
                <button type="button" class="small-btn" @click="backfillVectors">补齐一批向量</button>
              </div>

              <!-- Tab: 直播状况 -->
              <div v-if="activeTab === 'monitor'" class="tab-content">
                <div class="section-title">运行状态</div>
                <div class="status-grid">
                  <div class="status-item"><span class="s-label">AI 回复</span><span :class="['s-value', adminState.isSleeping ? 'off' : 'on']">{{ adminState.isSleeping ? '已暂停' : '正常' }}</span></div>
                  <div class="status-item"><span class="s-label">数字人</span><span class="s-value">{{ adminState.faceMode === 'mouse_tracking' ? '鼠标追踪' : '漫步' }}</span></div>
                  <div class="status-item"><span class="s-label">弹幕模式</span><span :class="['s-value', adminState.isVoiceMode ? 'highlight' : '']">{{ adminState.isVoiceMode ? '接管' : 'AI主播' }}</span></div>
                  <div class="status-item"><span class="s-label">管理员弹幕</span><span :class="['s-value', adminState.isHideAdmin ? 'warning' : '']">{{ adminState.isHideAdmin ? '隐藏' : '显示' }}</span></div>
                  <div class="status-item"><span class="s-label">音乐音量</span><span class="s-value">{{ Math.round(adminState.volume * 10) }}/10</span></div>
                  <div class="status-item"><span class="s-label">播放状态</span><span :class="['s-value', adminState.isPaused ? 'warning' : 'on']">{{ adminState.isPaused ? '暂停' : '播放中' }}</span></div>
                  <div class="status-item"><span class="s-label">运行平台</span><span :class="['s-value', liveState.running ? 'on' : 'off']">{{ liveState.running ? liveState.platform : '未启动' }}</span></div>
                </div>
                <button @click="refreshStatus" class="small-btn">刷新</button>

                <div class="section-title">管理员指令</div>
                <div class="command-grid">
                  <button class="cmd-btn green" @click="sendCommand('/sleep 1')" :disabled="adminState.isSleeping">暂停AI</button>
                  <button class="cmd-btn green" @click="sendCommand('/sleep 0')" :disabled="!adminState.isSleeping">恢复AI</button>
                  <button class="cmd-btn blue" @click="sendCommand('/face 1')" :disabled="adminState.faceMode === 'mouse_tracking'">鼠标追踪</button>
                  <button class="cmd-btn blue" @click="sendCommand('/face 0')" :disabled="adminState.faceMode === 'wandering'">漫步</button>
                  <button class="cmd-btn orange" @click="sendCommand('/voice 1')" :disabled="adminState.isVoiceMode">接管</button>
                  <button class="cmd-btn orange" @click="sendCommand('/voice 0')" :disabled="!adminState.isVoiceMode">AI主播</button>
                  <button class="cmd-btn gray" @click="sendCommand('/hide 1')" :disabled="adminState.isHideAdmin">隐藏管理</button>
                  <button class="cmd-btn gray" @click="sendCommand('/hide 0')" :disabled="!adminState.isHideAdmin">显示管理</button>
                  <button class="cmd-btn purple" @click="sendCommand('/next')">下一首</button>
                  <button class="cmd-btn purple" @click="sendCommand('/pause 1')" :disabled="adminState.isPaused">暂停音乐</button>
                  <button class="cmd-btn purple" @click="sendCommand('/pause 0')" :disabled="!adminState.isPaused">恢复音乐</button>
                  <button class="cmd-btn purple" @click="musicStore.setDuckingEnabled(!musicState.ducking_enabled)">
                    自动压低：{{ musicState.ducking_enabled ? '开' : '关' }}
                  </button>
                  <button class="cmd-btn red" @click="sendCommand('/rm')">移除当前</button>
                </div>
                <div class="command-line">
                  <label>音量:</label><input v-model.number="volumeInput" type="number" min="0" max="10" class="small-input" />
                  <button class="cmd-btn gray" @click="setVolume">设置</button>
                  <label>点歌:</label><input v-model="bvidInput" placeholder="BV号" class="small-input" />
                  <button class="cmd-btn green" :disabled="!bvidInput" @click="addMusic">添加</button>
                </div>

                <div class="section-title">测试平台事件 <span v-if="!testPlatformActive" class="hint">(当前运行平台不是 test，修改配置后请重启)</span></div>
                <div class="command-line">
                  <label>类型:</label>
                  <select v-model="testEventType" class="small-input" :disabled="!testPlatformActive">
                    <option value="danmaku">弹幕</option>
                    <option value="gift">礼物</option>
                    <option value="super_chat">醒目留言</option>
                    <option value="membership">会员</option>
                    <option value="follow">关注</option>
                    <option value="viewer_enter">进场</option>
                    <option value="like">点赞</option>
                    <option value="room_stats">房间统计</option>
                    <option value="live_ended">直播结束</option>
                  </select>
                  <template v-if="testEventNeedsUser">
                    <label>用户:</label><input v-model="testUser" class="small-input" style="width:100px" :disabled="!testPlatformActive" />
                    <label>用户 ID:</label><input v-model="testUserId" type="text" class="small-input" style="width:110px" :disabled="!testPlatformActive" />
                  </template>
                </div>
                <div v-if="testEventHasContent" class="command-line">
                  <label>内容:</label><input v-model="testContent" placeholder="弹幕或留言内容" class="flex-input" :disabled="!testPlatformActive" @keyup.enter="sendTestEvent" />
                </div>
                <div v-if="testEventHasGift" class="command-line">
                  <label>礼物:</label><input v-model="testGiftName" class="small-input" />
                  <label>数量:</label><input v-model.number="testGiftCount" type="number" min="1" class="small-input" />
                  <label>价值(元):</label><input v-model.number="testGiftValueYuan" type="number" min="0" step="0.01" class="small-input" />
                </div>
                <div v-if="testEventHasStats" class="command-line">
                  <label>{{ testEventType === 'room_stats' ? '观看人数:' : '数量:' }}</label>
                  <input v-model.number="testStatValue" type="number" min="0" class="small-input" />
                </div>
                <div class="command-line">
                  <button class="cmd-btn blue" :disabled="!canSendTestEvent" @click="sendTestEvent">发送标准事件</button>
                </div>

                <div class="section-title">实时日志</div>
                <div class="log-area">
                  <div v-for="(log, index) in logs" :key="index" :class="['log-item', log.type]">
                    <span class="log-time">{{ log.time }}</span>
                    <span class="log-content">{{ log.content }}</span>
                  </div>
                </div>
              </div>

              <!-- Tab: 记忆 -->
              <div v-if="activeTab === 'memory'" class="tab-content memory-tab-content">
                <MemoryDebugPanel />
              </div>
            </div>

            <div v-if="!['memory', 'overview'].includes(activeTab)" class="settings-footer">
              <div class="footer-left">
                <span v-if="saveStatus" :class="['save-status', saveStatus]">{{ saveStatusText }}</span>
              </div>
              <div class="footer-right">
                <button class="btn btn-secondary" @click="loadConfig">重新加载</button>
                <button class="btn btn-primary" @click="saveConfig">保存配置</button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, reactive } from 'vue'
import { storeToRefs } from 'pinia'
import type { FullConfig } from '../types/config'
import { MASKED } from '../types/config'
import { useNotification } from '@/utils/notification'
import { useMusicStore } from '@/features/music/store'
import { useConsoleTheme } from '@/composables/useConsoleTheme'
import MemoryDebugPanel from '@/components/memory/MemoryDebugPanel.vue'
import AgentSettingsPanel from '@/components/settings/agent/AgentSettingsPanel.vue'
import MusicManagementPanel from '@/components/settings/music/MusicManagementPanel.vue'

interface Props { visible?: boolean; embedded?: boolean }
const props = withDefaults(defineProps<Props>(), { visible: false, embedded: false })
const emit = defineEmits<{ close: []; saved: [] }>()

// ---- 依赖 ----
const musicStore = useMusicStore()
const { state: musicState } = storeToRefs(musicStore)
const { isLight, toggleTheme } = useConsoleTheme()

// ---- 连接状态（配置仅从后端获取，前端不缓存） ----
const connected = ref(false)
const connecting = ref(false)

// ---- Tabs ----
const tabs = [
  { key: 'overview', label: '运行总览' },
  { key: 'host', label: 'AI主播' },
  { key: 'ai_models', label: 'AI模型' },
  { key: 'tts', label: '语音' },
  { key: 'messaging', label: '消息调度' },
  { key: 'avatar', label: '数字人' },
  { key: 'agent_params', label: 'Agent 场景' },
  { key: 'music', label: '音乐' },
  { key: 'live', label: '直播' },
  { key: 'monitor', label: '直播状况' },
  { key: 'memory', label: '记忆' },
]
const activeTab = ref('overview')
const characters = ref<{ name: string }[]>([])
const saveStatus = ref('')
const credentialChecking = ref(false)
const credentialStatus = ref<{ valid: boolean; message: string } | null>(null)
const speechSchemas = ref<any[]>([])
const speechGatewayConfig = reactive<Record<string, any>>({ providers: {}, routes: {} })
const speechGatewayStatus = reactive<Record<string, any>>({ providers: {}, routes: {} })
const selectedSpeechProvider = ref('')
const speechFallbackProviders = ref<string[]>([])
const speechProviderDraft = reactive<Record<string, any>>({})
const speechGatewayBusy = ref(false)
const speechGatewayError = ref('')
const activeSpeechSchema = computed(() => {
  const provider = speechGatewayConfig.providers?.[selectedSpeechProvider.value]
  return provider ? speechSchemaByType(provider.type) : null
})
const selectedSpeechStatus = computed(() => speechGatewayStatus.providers?.[selectedSpeechProvider.value] || null)
const fallbackSpeechProviders = computed(() => Object.entries(speechGatewayConfig.providers || {})
  .filter(([name, provider]: [string, any]) => name !== selectedSpeechProvider.value && provider.enabled)
  .map(([name]) => name))

function speechSchemaByType(type: string) {
  return speechSchemas.value.find(schema => schema.type === type)
}

function selectSpeechProvider(updateModel = true) {
  const name = selectedSpeechProvider.value
  const provider = speechGatewayConfig.providers?.[name]
  const schema = provider ? speechSchemaByType(provider.type) : null
  Object.keys(speechProviderDraft).forEach(key => delete speechProviderDraft[key])
  for (const field of schema?.fields || []) {
    speechProviderDraft[field.key] = provider.values?.[field.key] ?? field.default ?? (field.type === 'boolean' ? false : '')
  }
  if (schema && name && updateModel) cfg.tts.model = 'host_voice'
}

async function loadSpeechGateway() {
  speechGatewayError.value = ''
  try {
    const [schemasResponse, configResponse, statusResponse] = await Promise.all([
      fetch('/speech-gateway/provider-schemas'),
      fetch('/speech-gateway/config'),
      fetch('/speech-gateway/status'),
    ])
    if (!schemasResponse.ok || !configResponse.ok || !statusResponse.ok) throw new Error('Speech Gateway 管理接口不可用')
    speechSchemas.value = (await schemasResponse.json()).data || []
    Object.assign(speechGatewayConfig, await configResponse.json())
    Object.assign(speechGatewayStatus, await statusResponse.json())
    const routePrimary = speechGatewayConfig.routes?.[cfg.tts.model]?.primary || ''
    const selectedTarget = cfg.tts.model.includes('/') ? cfg.tts.model : routePrimary
    const directProvider = selectedTarget.includes('/') ? selectedTarget.split('/', 1)[0] : ''
    selectedSpeechProvider.value = directProvider && speechGatewayConfig.providers[directProvider]
      ? directProvider
      : Object.keys(speechGatewayConfig.providers)[0] || ''
    speechFallbackProviders.value = (speechGatewayConfig.routes?.host_voice?.fallback || [])
      .map((target: string) => target.split('/', 1)[0])
      .filter((name: string) => name && name !== selectedSpeechProvider.value)
    selectSpeechProvider(false)
  } catch (error) {
    speechGatewayError.value = error instanceof Error ? error.message : String(error)
  }
}

async function saveSpeechProvider() {
  const name = selectedSpeechProvider.value
  const provider = speechGatewayConfig.providers?.[name]
  if (!name || !provider) return
  speechGatewayBusy.value = true
  speechGatewayError.value = ''
  try {
    const response = await fetch(`/speech-gateway/providers/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: provider.type, enabled: true, values: speechProviderDraft }),
    })
    if (!response.ok) throw new Error(await response.text())
    const schema = speechSchemaByType(provider.type)
    const primary = `${name}/${schema?.default_model || `${provider.type}-tts`}`
    const fallback = speechFallbackProviders.value.map(fallbackName => {
      const fallbackProvider = speechGatewayConfig.providers[fallbackName]
      const fallbackSchema = speechSchemaByType(fallbackProvider.type)
      return `${fallbackName}/${fallbackSchema?.default_model || `${fallbackProvider.type}-tts`}`
    })
    const routeResponse = await fetch('/speech-gateway/routes/host_voice', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ primary, fallback }),
    })
    if (!routeResponse.ok) throw new Error(await routeResponse.text())
    cfg.tts.model = 'host_voice'
    useNotification().success('TTS 提供者与 fallback 路由已保存并热加载')
    await loadSpeechGateway()
  } catch (error) {
    speechGatewayError.value = error instanceof Error ? error.message : String(error)
  } finally {
    speechGatewayBusy.value = false
  }
}

async function probeSpeechProvider() {
  if (!selectedSpeechProvider.value) return
  speechGatewayBusy.value = true
  try {
    const response = await fetch(`/speech-gateway/providers/${encodeURIComponent(selectedSpeechProvider.value)}/probe`, { method: 'POST' })
    const result = await response.json()
    if (!response.ok || !result.healthy) throw new Error(result.detail || '提供者探测失败')
    useNotification().success('TTS 提供者探测成功，熔断状态已恢复')
    await loadSpeechGateway()
  } catch (error) {
    speechGatewayError.value = error instanceof Error ? error.message : String(error)
  } finally {
    speechGatewayBusy.value = false
  }
}

function setLocalDirectories(event: Event) {
  cfg.music.local_directories = (event.target as HTMLTextAreaElement).value
    .split(/\r?\n/)
    .map(value => value.trim())
    .filter(Boolean)
}
const saveStatusText = ref('')
const vectorStatus = reactive({ available: false, vector_count: 0 })
const avatarPreviewRevision = ref(Date.now())
const avatarRuntimeState = reactive({ state: 'stopped', error: '' })
const runtimeHealth = reactive<Record<string, any>>({ status: 'unknown', components: {}, message_queue: {} })
const agentRuntime = reactive<Record<string, any>>({ running: false, runtime_status: 'unknown', events: {} })
const aiRuntime = reactive<Record<string, any>>({ buffer_size: 0, unanswered_count: 0, playback: {} })
const runtimeBusy = ref('')
const runtimeUpdatedAt = ref('')
const avatarPreviewUrl = computed(() => `/avatar/preview/frame?v=${avatarPreviewRevision.value}`)
const avatarStatusText = computed(() => {
  if (avatarRuntimeState.state === 'running') return 'FeinaAvatar 运行中'
  if (avatarRuntimeState.state === 'starting') return '渲染器启动中'
  if (avatarRuntimeState.state === 'failed') return avatarRuntimeState.error || '渲染器启动失败'
  return '当前无预览帧'
})

// ---- 配置（仅用于绑定 UI，不持久化存储） ----
const cfg = reactive<FullConfig>({} as FullConfig)

function initCfgShape() {
  // 初始化 Vue reactive 所需的结构（值会被后端覆盖）
  const s: Record<string, any> = {
    live: { platform: 'bilibili' },
    bilibili: { room_id: 0, sessdata: '', uid: 0 },
    douyin: { web_rid: '', cookie: '' },
    host: { reply_interval: 5, max_reply_length: 100, api_url: '', api_key: '', model: '', temperature: 0.7, top_p: 0.9, max_tokens: 200, disable_thinking: true },
    llm: { api_url: '', api_key: '', model: '', temperature: 0.1, top_p: 0.9, max_tokens: 200, disable_thinking: true },
    tts: { gateway_url: 'http://127.0.0.1:8091/v1', api_key: '', model: 'host_voice', response_format: 'mp3', speed: 1.0, timeout_seconds: 60 },
    agent: { enabled: false, scenario_id: 'slay_the_spire', mcp_url: 'http://127.0.0.1:8080', api_url: '', api_key: '', model: '', temperature: 0.4, max_tokens: 500, disable_thinking: true, poll_interval: 1.0, memory_threshold: 30, memory_idle_seconds: 120, memory_scan_interval_seconds: 30, memory_context_max_chars: 12000, min_step_interval: 3.0, step_jitter: 0.5, commentary_interval: 30.0, min_commentary_interval: 15.0, commentary_hold_timeout: 20.0, memory_eagerness: 3, queue_max_size: 20, host_history_maxlen: 50, action_history_maxlen: 30, scenario_config: { default_character: 'IRONCLAD' } },
    avatar: { enabled: true, character: 'feina00', motion: { source: 'autonomous', allow_browser_control: true }, lip_sync: { source: 'browser_audio', sensitivity: 3, noise_gate: 0.015, attack_ms: 35, release_ms: 90 }, renderer: { engine: 'feina_avatar', model: 'tha3', backend: 'onnxruntime', precision: 'fp32', separable: false, use_eyebrow: true, frame_rate: 30, interpolation: 1, super_resolution: 1, ram_cache_mb: 2048, vram_cache_mb: 2048 }, outputs: { spout: { enabled: true, name: 'FeinaAvatar' }, preview: { enabled: true, frame_rate: 10, quality: 80 } } },
    ai: { max_history_per_session: 16, summary_interval: 10, summary_idle_seconds: 300.0, summary_scan_interval_seconds: 60.0, max_recent_messages: 16, poll_interval_seconds: 10.0 },
    messaging: { danmaku_starvation_seconds: 30.0, danmaku_flood_threshold: 5, danmaku_flood_window: 20.0, gift_starvation_seconds: 60.0, gift_flood_threshold: 3, gift_flood_window: 30.0, gift_value_highest: 10000, gift_value_high: 5000, gift_value_normal: 1000, gift_value_low: 100, user_cooldown_seconds: 3.0, default_ttl_seconds: 30.0, rate_limit_commentary: 4.0, rate_limit_danmaku: 3.0, rate_limit_gift: 10.0 },
    music: { default_provider: 'auto', min_duration_seconds: 60, max_duration_seconds: 480, queue_capacity: 5, per_user_limit: 2, allow_bare_bv: false, accept_score: 60, reject_score: -50, llm_min_confidence: 0.75, search_candidates: 5, ducking_factor: 0.2, ducking_enabled: true, local_directories: [] },
    storage: { sqlite_path: 'data/feinalive.db', chroma_path: 'data/chroma', chroma_collection: 'memory_atoms' },
    announcement: '',
    admin: { username: '', identities: { bilibili: '', douyin: '', test: 'internal' } },
    embedding: { model: '', api_url: '', api_key: '', dimensions: null, user_graph_enabled: true, game_graph_enabled: true },
  }
  Object.assign(cfg, s)
}

// ---- 从后端加载配置 ----
async function loadConfig() {
  connecting.value = true
  connected.value = false
  saveStatus.value = ''
  saveStatusText.value = ''

  initCfgShape()

  try {
    const res = await fetch('/config')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    Object.assign(cfg, data)
    cfg.agent.scenario_config ||= {}
    connected.value = true
    await loadSpeechGateway()
  } catch (e) {
    console.error('连接后端失败:', e)
    connected.value = false
  } finally {
    connecting.value = false
  }
}

async function loadCharacters() {
  try {
    const res = await fetch('/config/avatar/characters')
    const data = await res.json()
    characters.value = data.characters || []
  } catch { /* ignore */ }
}

async function refreshAvatarStatus() {
  try {
    const response = await fetch('/avatar/status')
    const data = await response.json()
    avatarRuntimeState.state = data.state || 'stopped'
    avatarRuntimeState.error = data.error || ''
  } catch {
    avatarRuntimeState.state = 'stopped'
  }
}

async function refreshOverview() {
  if (runtimeBusy.value) return
  runtimeBusy.value = 'refresh'
  try {
    const [healthResponse, agentResponse, aiResponse, liveResponse] = await Promise.all([
      fetch('/health'),
      fetch('/agent/status'),
      fetch('/ai/status'),
      fetch('/live/state'),
    ])
    if (healthResponse.ok) Object.assign(runtimeHealth, await healthResponse.json())
    if (agentResponse.ok) Object.assign(agentRuntime, await agentResponse.json())
    if (aiResponse.ok) Object.assign(aiRuntime, await aiResponse.json())
    if (liveResponse.ok) {
      const state = await liveResponse.json()
      liveState.running = Boolean(state.running)
      liveState.platform = state.context?.platform || ''
    }
    await Promise.all([musicStore.fetchState(), refreshAvatarStatus()])
    runtimeUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    useNotification().error(`运行状态刷新失败：${error instanceof Error ? error.message : String(error)}`)
  } finally {
    runtimeBusy.value = ''
  }
}

async function toggleAgent() {
  runtimeBusy.value = 'agent'
  try {
    const response = await fetch(agentRuntime.running ? '/agent/stop' : '/agent/start', { method: 'POST' })
    const result = await response.json()
    if (!response.ok || result.success === false) throw new Error(result.message || `HTTP ${response.status}`)
    useNotification().success(result.message || 'Agent 状态已更新')
  } catch (error) {
    useNotification().error(error instanceof Error ? error.message : String(error))
  } finally {
    runtimeBusy.value = ''
    await refreshOverview()
  }
}

async function toggleAvatar() {
  runtimeBusy.value = 'avatar'
  try {
    const action = avatarRuntimeState.state === 'running' ? 'stop' : 'start'
    const response = await fetch(`/avatar/${action}`, { method: 'POST' })
    const result = await response.json()
    if (!response.ok || result.state === 'failed') throw new Error(result.error || `HTTP ${response.status}`)
  } catch (error) {
    useNotification().error(error instanceof Error ? error.message : String(error))
  } finally {
    runtimeBusy.value = ''
    await refreshOverview()
  }
}

function openLiveDisplay() {
  const port = window.location.port === '5174' ? '5173' : window.location.port === '8089' ? '8088' : ''
  const origin = `${window.location.protocol}//${window.location.hostname}${port ? `:${port}` : ''}`
  window.open(origin, '_blank', 'noopener,noreferrer')
}

async function refreshVectorStatus() {
  try {
    const response = await fetch('/ai/memory/vector/status')
    Object.assign(vectorStatus, await response.json())
  } catch { vectorStatus.available = false }
}

async function backfillVectors() {
  try {
    await fetch('/ai/memory/vector/backfill?batch_size=50', { method: 'POST' })
    await refreshVectorStatus()
    useNotification().success('向量补齐任务已执行')
  } catch { useNotification().error('向量补齐失败') }
}

async function openImagesFolder() {
  try {
    await fetch('/config/avatar/open-images', { method: 'POST' })
  } catch { /* ignore */ }
}

// ---- 保存配置到后端 ----
async function saveConfig() {
  saveStatus.value = 'saving'
  saveStatusText.value = '保存中...'
  try {
    const res = await fetch('/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg),
    })
    if (res.ok) {
      const data = await res.json()
      Object.assign(cfg, data) // 用后端 canonical 数据覆盖
      cfg.agent.scenario_config ||= {}
      saveStatus.value = 'ok'
      saveStatusText.value = data.restart_required || res.headers.get('X-Restart-Required') === 'true'
        ? '已保存；场景、MCP 或能力配置需重启应用后生效'
        : '已保存'
      emit('saved')
    } else {
      const errText = await res.text()
      saveStatus.value = 'err'
      saveStatusText.value = '保存失败: ' + errText
    }
  } catch (e) {
    saveStatus.value = 'err'
    saveStatusText.value = '保存失败: ' + e
  }
  setTimeout(() => { saveStatus.value = ''; saveStatusText.value = '' }, 3000)
}

function close() {
  emit('close')
}

// ---- 直播状况（运行时监测，不受连接状态影响） ----
interface LogItem { time: string; content: string; type: 'danmaku' | 'reply' | 'system' | 'error' }
type TestEventType = 'danmaku' | 'gift' | 'super_chat' | 'membership' | 'follow' | 'viewer_enter' | 'like' | 'room_stats' | 'live_ended'
const testEventType = ref<TestEventType>('danmaku')
const testUser = ref('测试观众')
const testUserId = ref('viewer-123456')
const testContent = ref('')
const testGiftName = ref('小花花')
const testGiftCount = ref(1)
const testGiftValueYuan = ref(0)
const testStatValue = ref(1)
const volumeInput = ref(10)
const bvidInput = ref('')
const adminState = ref({ isSleeping: false, faceMode: 'wandering', isVoiceMode: false, isHideAdmin: false, volume: 1.0, isPaused: false })
const liveState = reactive({ running: false, platform: '' })
const testPlatformActive = computed(() => liveState.running && liveState.platform === 'test')
const testEventNeedsUser = computed(() => !['room_stats', 'live_ended'].includes(testEventType.value))
const testEventHasContent = computed(() => ['danmaku', 'super_chat'].includes(testEventType.value))
const testEventHasGift = computed(() => ['gift', 'super_chat', 'membership'].includes(testEventType.value))
const testEventHasStats = computed(() => ['like', 'room_stats'].includes(testEventType.value))
const canSendTestEvent = computed(() => {
  if (!testPlatformActive.value) return false
  if (testEventNeedsUser.value && (!testUser.value.trim() || !testUserId.value.trim())) return false
  if (testEventType.value === 'danmaku' && !testContent.value.trim()) return false
  return true
})
const logs = ref<LogItem[]>([])
let ws: WebSocket | null = null
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null
let shouldReconnect = true
let avatarPreviewTimer: ReturnType<typeof setInterval> | null = null
let overviewTimer: ReturnType<typeof setInterval> | null = null

function addLog(content: string, type: LogItem['type'] = 'system') {
  const now = new Date()
  const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
  logs.value.push({ time, content, type })
  if (logs.value.length > 100) logs.value = logs.value.slice(-100)
}

function connectWebSocket() {
  if (!shouldReconnect) return
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${window.location.host}/live/ws`)
  ws.onopen = () => addLog('WebSocket 已连接', 'system')
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'live_event') {
        const liveEvent = msg.data
        const user = liveEvent.user?.display_name ? `${liveEvent.user.display_name}: ` : ''
        const detail = liveEvent.gift
          ? `${liveEvent.gift.name} x${liveEvent.gift.count}`
          : liveEvent.content || JSON.stringify(liveEvent.stats || {})
        addLog(`[${liveEvent.type}] ${user}${detail}`, liveEvent.type === 'danmaku' ? 'danmaku' : 'system')
      }
      else if (msg.type === 'start') addLog('[AI] 开始生成回复...', 'system')
      else if (msg.type === 'text') addLog(`[AI] ${msg.text ?? msg.data?.text ?? ''}`, 'reply')
      else if (msg.type === 'audio') addLog('[AI] 音频已生成', 'system')
      else if (msg.type === 'end') addLog('[AI] 回复完成', 'system')
      else if (msg.type === 'error') addLog(`[错误] ${msg.data?.text || ''}`, 'error')
      else if (msg.type === 'music_state') {
        musicStore.applyExternalState(msg.data)
        addLog(`[音乐] 状态更新 #${msg.data.revision}`, 'system')
      } else if (msg.type === 'music_added') { musicStore.fetchState(); addLog(`[点歌] ${(msg.data.title || '').replace(/\n/g,' ').trim()}`, 'system') }
      else if (msg.type === 'music_error') addLog(`[点歌失败] ${msg.data.error}`, 'error')
    } catch { /* */ }
  }
  ws.onerror = () => addLog('WebSocket 连接错误', 'error')
  ws.onclose = () => {
    addLog('WebSocket 已断开', 'system')
    ws = null
    if (shouldReconnect) wsReconnectTimer = setTimeout(connectWebSocket, 3000)
  }
}

async function verifyPlatformCredentials() {
  if (cfg.live.platform === 'test') return
  credentialChecking.value = true
  credentialStatus.value = null
  try {
    const response = await fetch(`/live/platforms/${cfg.live.platform}/verify`)
    const result = await response.json()
    credentialStatus.value = {
      valid: Boolean(result.valid),
      message: result.valid
        ? (result.username ? `连接有效：${result.username}` : '直播间连接信息有效')
        : (result.error || '验证失败'),
    }
  } catch (error) {
    credentialStatus.value = { valid: false, message: error instanceof Error ? error.message : String(error) }
  } finally {
    credentialChecking.value = false
  }
}

async function sendTestEvent() {
  if (!canSendTestEvent.value) return
  const stats = testEventType.value === 'room_stats'
    ? { viewer_count: testStatValue.value }
    : testEventType.value === 'like'
      ? { count: testStatValue.value }
      : {}
  try {
    const res = await fetch('/test/live/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: testEventType.value,
        user: testUser.value,
        user_id: testUserId.value,
        content: testContent.value,
        gift_name: testGiftName.value,
        gift_count: testGiftCount.value,
        value_minor: Math.max(0, Math.round(testGiftValueYuan.value * 100)),
        stats,
      }),
    })
    const result = await res.json()
    if (!res.ok || !result.success) throw new Error(result.detail || '事件被拒绝')
    addLog(`[已提交] ${result.event.type} ${result.event.event_id}`, 'system')
    if (testEventType.value === 'danmaku') testContent.value = ''
    refreshStatus()
  } catch (error) {
    useNotification().error(error instanceof Error ? error.message : '发送测试事件失败')
  }
}

async function sendCommand(command: string) {
  try {
    const res = await fetch('/ai/admin/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command }) })
    const result = await res.json()
    if (result.success) {
      if (result.state) adminState.value = { isSleeping: result.state.is_sleeping, faceMode: result.state.face_mode, isVoiceMode: result.state.is_voice_mode, isHideAdmin: result.state.is_hide_admin, volume: result.state.volume ?? 1.0, isPaused: result.state.is_paused ?? false }
      addLog(`[指令] ${command} -> ${result.message}`, 'system')
    } else addLog(`[错误] ${command} -> ${result.message}`, 'error')
  } catch { useNotification().error('发送指令失败') }
}

async function refreshStatus() {
  try {
    const [adminResponse, liveResponse] = await Promise.all([
      fetch('/ai/admin/state'),
      fetch('/live/state'),
    ])
    const data = await adminResponse.json()
    const currentLiveState = await liveResponse.json()
    adminState.value = { isSleeping: data.is_sleeping, faceMode: data.face_mode, isVoiceMode: data.is_voice_mode, isHideAdmin: data.is_hide_admin, volume: data.volume ?? 1.0, isPaused: data.is_paused ?? false }
    liveState.running = !!currentLiveState.running
    liveState.platform = currentLiveState.context?.platform || ''
    volumeInput.value = Math.round((data.volume ?? 1.0) * 10)
  } catch { /* */ }
}

async function setVolume() { await sendCommand(`/sound ${volumeInput.value}`) }
async function addMusic() { if (bvidInput.value) { await sendCommand(`/add_music ${bvidInput.value}`); bvidInput.value = '' } }

// ---- 生命周期 ----
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.visible && !props.embedded) close()
}

watch(() => props.visible, (visible) => {
  if (visible || props.embedded) {
    loadConfig()
    loadCharacters()
    refreshStatus()
    refreshVectorStatus()
    refreshAvatarStatus()
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  connectWebSocket()
  refreshStatus()
  refreshVectorStatus()
  refreshAvatarStatus()
  if (props.visible || props.embedded) {
    void loadConfig().then(() => {
      if (connected.value) void refreshOverview()
    })
    loadCharacters()
  }
  avatarPreviewTimer = setInterval(() => {
    if (!props.visible || activeTab.value !== 'avatar') return
    avatarPreviewRevision.value = Date.now()
    void refreshAvatarStatus()
  }, 1000)
  overviewTimer = setInterval(() => {
    if ((!props.visible && !props.embedded) || !connected.value) return
    void refreshOverview()
  }, 5000)
})

onUnmounted(() => {
  shouldReconnect = false
  if (wsReconnectTimer) clearTimeout(wsReconnectTimer)
  if (avatarPreviewTimer) clearInterval(avatarPreviewTimer)
  if (overviewTimer) clearInterval(overviewTimer)
  window.removeEventListener('keydown', handleKeydown)
  if (ws) ws.close()
})
</script>

<style scoped>
.settings-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.settings-panel {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 16px;
  width: 680px;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  color-scheme: dark;
}

.settings-panel-wide {
  width: min(1500px, 94vw);
  height: min(920px, 92vh);
}

.avatar-preview {
  display: grid;
  grid-template-columns: minmax(220px, 420px) 1fr;
  align-items: center;
  gap: 18px;
  margin: 10px 0 18px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.7);
}

.avatar-preview img {
  width: 100%;
  max-height: 360px;
  object-fit: contain;
  border-radius: 8px;
  background: repeating-conic-gradient(#334155 0 25%, #1e293b 0 50%) 50% / 18px 18px;
}

.avatar-preview span { color: #94a3b8; font-size: 13px; }

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.settings-header h2 { color: #f1f5f9; font-size: 18px; font-weight: 600; }

.close-btn { background: none; border: none; color: #94a3b8; font-size: 26px; cursor: pointer; padding: 0; line-height: 1; }
.close-btn:hover { color: #f1f5f9; }

/* ---- 连接状态 ---- */
.connect-state { display: flex; align-items: center; justify-content: center; min-height: 300px; }

.connect-box { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.connect-box p { color: #94a3b8; font-size: 14px; margin: 0; }
.connect-box .hint { color: #64748b; font-size: 12px; }
.connect-error p:first-of-type { color: #f87171; font-weight: 600; }

.spinner {
  width: 36px; height: 36px;
  border: 3px solid rgba(255,255,255,0.1);
  border-top: 3px solid #60a5fa;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.err-icon {
  width: 48px; height: 48px;
  border-radius: 50%;
  background: rgba(248,113,113,0.15);
  color: #f87171;
  font-size: 28px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ---- Tabs + Content ---- */
.settings-tabs {
  display: flex;
  gap: 2px;
  padding: 10px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  overflow-x: auto;
  flex-shrink: 0;
}

.tab-btn {
  padding: 7px 12px;
  background: transparent;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  border-radius: 8px;
  font-size: 12.5px;
  white-space: nowrap;
  transition: all 0.2s;
}
.tab-btn:hover { background: rgba(255,255,255,0.05); color: #f1f5f9; }
.tab-btn.active { background: rgba(59,130,246,0.2); color: #60a5fa; }

.settings-content { flex: 1; overflow-y: auto; padding: 18px 24px; }
.tab-content { display: flex; flex-direction: column; gap: 14px; }
.settings-content-memory {
  padding: 16px;
  overflow: hidden;
}
.memory-tab-content {
  height: 100%;
  min-height: 0;
}

.section-title {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding-top: 6px;
  margin-top: 2px;
}
.section-title:first-child { padding-top: 0; margin-top: 0; }

.section-desc { color: #94a3b8; font-size: 12px; margin: -8px 0 2px 0; }

.form-group { display: flex; flex-direction: column; gap: 5px; }

.form-group label { color: #cbd5e1; font-size: 12.5px; display: flex; align-items: center; gap: 6px; }
.checkbox-label { flex-direction: row !important; cursor: pointer; }
.hint { color: #94a3b8; font-size: 11px; font-weight: 400; }
.range-value { color: #60a5fa; font-size: 12px; font-weight: 600; }

.form-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

.form-group input[type="text"],
.form-group input[type="number"],
.form-group input[type="password"],
.form-group select {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  padding: 7px 10px;
  color: #f1f5f9;
  font-size: 12.5px;
  color-scheme: dark;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.flex-select {
  flex: 1;
  min-width: 0;
}

.form-group input:focus, .form-group select:focus { outline: none; border-color: #3b82f6; }

/* 下拉选项深色背景 */
.form-group select option,
select option {
  background: #1e293b;
  color: #e2e8f0;
}
.form-group input[type="range"] { width: 100%; accent-color: #3b82f6; }
.form-group input[type="checkbox"] { accent-color: #3b82f6; width: 15px; height: 15px; }

.readonly-field { opacity: 0.5; cursor: not-allowed; }

.textarea-field {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  padding: 8px 10px;
  color: #f1f5f9;
  font-size: 12.5px;
  resize: vertical;
  font-family: inherit;
}
.textarea-field:focus { outline: none; border-color: #3b82f6; }

.dimmed { opacity: 0.4; }

.compact-table { width: 100%; border-collapse: collapse; }
.compact-table td { padding: 4px 0; }
.compact-table td:first-child { width: 50%; }
.compact-table input {
  width: 100%; box-sizing: border-box;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 6px;
  padding: 5px 8px;
  color: #f1f5f9;
  font-size: 12px;
}
.compact-table input:focus { outline: none; border-color: #3b82f6; }

/* Status grid */
.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.status-item { display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; padding: 8px 12px; }
.s-label { color: #94a3b8; font-size: 12px; }
.s-value { font-size: 12px; font-weight: 600; }
.s-value.on { color: #4ade80; }
.s-value.off { color: #f87171; }
.s-value.highlight { color: #fbbf24; }
.s-value.warning { color: #fb923c; }

.command-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
.cmd-btn { padding: 6px 10px; border: none; border-radius: 6px; font-size: 11.5px; cursor: pointer; color: white; transition: opacity 0.2s; }
.cmd-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.cmd-btn.green { background: #22c55e; }
.cmd-btn.blue { background: #3b82f6; }
.cmd-btn.orange { background: #f59e0b; }
.cmd-btn.gray { background: #64748b; }
.cmd-btn.purple { background: #8b5cf6; }
.cmd-btn.red { background: #ef4444; }
.cmd-btn.cyan { background: #06b6d4; }

.command-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.command-line label { color: #94a3b8; font-size: 12px; white-space: nowrap; }

.small-input { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 5px 8px; color: #f1f5f9; font-size: 12px; width: 100px; }
.small-input:focus { outline: none; border-color: #3b82f6; }
.flex-input { flex: 1; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 5px 8px; color: #f1f5f9; font-size: 12px; }
.flex-input:focus { outline: none; border-color: #3b82f6; }

.small-btn { padding: 6px 14px; background: #64748b; border: none; border-radius: 6px; color: white; font-size: 12px; cursor: pointer; align-self: flex-start; }
.connection-check { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.credential-status { font-size: 12px; line-height: 1.5; }
.credential-status.ok { color: #86efac; }
.credential-status.bad { color: #fca5a5; }

.log-area { max-height: 140px; overflow-y: auto; background: rgba(0,0,0,0.4); border-radius: 8px; padding: 8px; font-family: monospace; font-size: 11px; }
.log-item { display: flex; gap: 8px; padding: 2px 0; }
.log-item.danmaku { color: #4fc3f7; }
.log-item.reply { color: #81c784; }
.log-item.system { color: #94a3b8; }
.log-item.error { color: #ef5350; }
.log-time { color: #475569; flex-shrink: 0; }

/* Footer */
.settings-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
}
.footer-left { flex: 1; }
.footer-right { display: flex; gap: 10px; }

.save-status { font-size: 12px; padding: 4px 10px; border-radius: 6px; }
.save-status.ok { color: #4ade80; background: rgba(74,222,128,0.1); }
.save-status.err { color: #f87171; background: rgba(248,113,113,0.1); }
.save-status.saving { color: #fbbf24; background: rgba(251,191,36,0.1); }

.btn { padding: 8px 18px; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.btn-primary { background: #3b82f6; color: white; border: none; }
.btn-primary:hover { background: #2563eb; }
.btn-secondary { background: transparent; color: #94a3b8; border: 1px solid rgba(255,255,255,0.1); }
.btn-secondary:hover { background: rgba(255,255,255,0.05); color: #f1f5f9; }

.modal-enter-active, .modal-leave-active { transition: opacity 0.2s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }

.settings-content::-webkit-scrollbar { width: 5px; }
.settings-content::-webkit-scrollbar-track { background: transparent; }
.settings-content::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
.mobile-tab-picker { display: none; }

/* ---- Standalone operations console ---- */
.settings-overlay.is-embedded {
  position: relative;
  inset: auto;
  min-height: 100dvh;
  padding: 24px;
  display: block;
  background: transparent;
  backdrop-filter: none;
  z-index: auto;
}

.settings-panel.is-embedded {
  width: min(1680px, 100%);
  height: calc(100dvh - 48px);
  min-height: 680px;
  max-height: none;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr);
  grid-template-rows: 76px minmax(0, 1fr) auto;
  overflow: hidden;
  border: 1px solid rgba(167, 139, 250, 0.16);
  border-radius: 20px;
  background: linear-gradient(145deg, rgba(19, 25, 40, 0.98), rgba(10, 15, 27, 0.99));
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.42);
}

.is-embedded .settings-header {
  grid-column: 1 / -1;
  grid-row: 1;
  padding: 14px 20px;
  background: rgba(10, 15, 27, 0.72);
}

.console-brand,
.header-meta,
.runtime-card-head,
.overview-actions,
.card-actions {
  display: flex;
  align-items: center;
}

.console-brand { gap: 12px; }
.console-brand > div { display: flex; flex-direction: column; gap: 2px; }
.console-brand span { color: #a78bfa; font-size: 10px; font-weight: 700; letter-spacing: .16em; }
.console-brand h2 { margin: 0; font-size: 17px; letter-spacing: .02em; }
.brand-mark { width: 34px; height: 34px; border-radius: 11px; background: linear-gradient(135deg, #7c3aed, #ec4899); box-shadow: 0 8px 24px rgba(124, 58, 237, .28); }
.brand-mark::after { content: ''; display: block; width: 10px; height: 10px; margin: 12px; border: 2px solid white; border-radius: 50%; }
.header-meta { gap: 12px; }
.theme-toggle { min-width: 82px; min-height: 40px; padding: 7px 11px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; border: 1px solid rgba(167, 139, 250, .2); border-radius: 10px; color: #ddd6fe; background: rgba(124, 58, 237, .08); cursor: pointer; transition: color .18s ease, border-color .18s ease, background-color .18s ease; }
.theme-toggle:hover { border-color: rgba(167, 139, 250, .48); background: rgba(124, 58, 237, .16); }
.theme-toggle:focus-visible { outline: 2px solid #a78bfa; outline-offset: 2px; }
.theme-toggle svg { width: 17px; height: 17px; }
.theme-toggle span { color: inherit; font-size: 11px; font-weight: 600; letter-spacing: 0; }
.connection-pill { min-height: 28px; padding: 5px 10px; border: 1px solid; border-radius: 999px; font-size: 11px; font-weight: 600; }
.connection-pill.online { color: #86efac; border-color: rgba(74, 222, 128, .28); background: rgba(34, 197, 94, .09); }
.connection-pill.offline { color: #fca5a5; border-color: rgba(248, 113, 113, .28); background: rgba(239, 68, 68, .09); }

.is-embedded .settings-tabs {
  grid-column: 1;
  grid-row: 2 / 4;
  min-width: 0;
  padding: 18px 12px;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  overflow: auto;
  border-right: 1px solid rgba(255, 255, 255, .07);
  border-bottom: 0;
  background: rgba(7, 11, 21, .4);
}

.is-embedded .tab-btn {
  position: relative;
  min-height: 44px;
  padding: 10px 14px 10px 24px;
  border-radius: 10px;
  text-align: left;
  color: #9ca3af;
  font-size: 13px;
  transition: color .18s ease, background-color .18s ease;
}
.is-embedded .tab-btn:hover { color: #f3f4f6; background: rgba(255, 255, 255, .045); }
.is-embedded .tab-btn.active { color: #ede9fe; background: linear-gradient(90deg, rgba(124, 58, 237, .22), rgba(124, 58, 237, .06)); }
.tab-indicator { position: absolute; left: 10px; width: 5px; height: 5px; border-radius: 50%; background: #4b5563; }
.tab-btn.active .tab-indicator { background: #c4b5fd; box-shadow: 0 0 10px rgba(167, 139, 250, .8); }

.is-embedded .settings-content {
  grid-column: 2;
  grid-row: 2;
  min-width: 0;
  padding: 28px 32px;
  background: rgba(15, 21, 35, .36);
}
.is-embedded .connect-state { grid-column: 1 / -1; grid-row: 2 / 4; }
.is-embedded .settings-footer { grid-column: 2; grid-row: 3; min-height: 68px; padding: 12px 32px; background: rgba(10, 15, 27, .82); }
.is-embedded .form-group input[type='text'],
.is-embedded .form-group input[type='number'],
.is-embedded .form-group input[type='password'],
.is-embedded .form-group select,
.is-embedded .textarea-field,
.is-embedded .small-input,
.is-embedded .flex-input { min-height: 44px; border-color: rgba(255, 255, 255, .12); background: rgba(255, 255, 255, .045); }
.is-embedded .btn,
.is-embedded .small-btn,
.is-embedded .cmd-btn { min-height: 44px; }
.is-embedded .btn-primary { background: linear-gradient(135deg, #7c3aed, #6d28d9); box-shadow: 0 8px 22px rgba(124, 58, 237, .22); }
.is-embedded .btn-primary:hover { background: linear-gradient(135deg, #8b5cf6, #7c3aed); }

.overview-content { gap: 24px; }
.overview-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; }
.overview-heading .eyebrow { color: #a78bfa; font-size: 10px; font-weight: 700; letter-spacing: .14em; }
.overview-heading h1 { margin: 6px 0 6px; color: #f8fafc; font-size: clamp(22px, 2.4vw, 32px); line-height: 1.2; }
.overview-heading p { max-width: 620px; margin: 0; color: #94a3b8; font-size: 13px; line-height: 1.65; }
.overview-actions { justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
.last-updated { width: 100%; color: #64748b; font-size: 11px; text-align: right; font-variant-numeric: tabular-nums; }
.runtime-grid { display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 14px; }
.runtime-card { min-height: 166px; padding: 18px; display: flex; flex-direction: column; gap: 10px; border: 1px solid rgba(255, 255, 255, .08); border-radius: 14px; background: linear-gradient(145deg, rgba(255, 255, 255, .045), rgba(255, 255, 255, .018)); box-shadow: inset 0 1px rgba(255, 255, 255, .025); }
.runtime-card-head { gap: 8px; color: #9ca3af; font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
.runtime-dot { width: 8px; height: 8px; border-radius: 50%; background: #64748b; }
.runtime-dot.ok { background: #4ade80; box-shadow: 0 0 12px rgba(74, 222, 128, .55); }
.runtime-dot.bad { background: #fb7185; box-shadow: 0 0 12px rgba(251, 113, 133, .45); }
.runtime-dot.idle { background: #fbbf24; }
.runtime-card strong { overflow: hidden; color: #f8fafc; font-size: 17px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.runtime-card p { min-height: 38px; margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.6; }
.card-action { min-height: 38px; padding: 7px 12px; align-self: flex-start; border: 1px solid rgba(167, 139, 250, .2); border-radius: 8px; color: #ddd6fe; background: rgba(124, 58, 237, .09); cursor: pointer; transition: background-color .18s ease, border-color .18s ease; }
.card-action:hover { border-color: rgba(167, 139, 250, .45); background: rgba(124, 58, 237, .18); }
.card-action:disabled { opacity: .42; cursor: not-allowed; }
.card-actions { gap: 8px; }
.settings-subcard { margin: 16px 0; padding: 16px; border: 1px solid rgba(167, 139, 250, .18); border-radius: 12px; background: rgba(124, 58, 237, .045); }
.action-btn { min-height: 38px; padding: 8px 14px; border: 1px solid rgba(167, 139, 250, .28); border-radius: 8px; color: #ede9fe; background: rgba(124, 58, 237, .16); cursor: pointer; }
.action-btn:disabled { opacity: .45; cursor: not-allowed; }
.status-error { color: #fb7185; font-size: 12px; }

@media (max-width: 1180px) {
  .runtime-grid { grid-template-columns: repeat(2, minmax(220px, 1fr)); }
  .overview-heading { flex-direction: column; }
  .overview-actions { justify-content: flex-start; }
  .last-updated { text-align: left; }
}

@media (max-width: 860px) {
  .settings-overlay.is-embedded { padding: 0; }
  .settings-panel.is-embedded { width: 100%; height: 100dvh; min-height: 620px; border: 0; border-radius: 0; grid-template-columns: minmax(0, 1fr); grid-template-rows: 68px auto minmax(0, 1fr) auto; }
  .is-embedded .settings-header { grid-column: 1; grid-row: 1; padding: 10px 16px; }
  .is-embedded .settings-tabs { display: none; }
  .is-embedded .mobile-tab-picker { grid-column: 1; grid-row: 2; min-height: 64px; padding: 10px 16px; display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 12px; border-bottom: 1px solid rgba(255, 255, 255, .07); background: rgba(7, 11, 21, .56); }
  .mobile-tab-picker span { color: #94a3b8; font-size: 12px; font-weight: 600; }
  .mobile-tab-picker select { width: 100%; min-height: 44px; padding: 8px 12px; border: 1px solid rgba(167, 139, 250, .24); border-radius: 10px; color: #ede9fe; background: #171426; color-scheme: dark; }
  .is-embedded .settings-content { grid-column: 1; grid-row: 3; padding: 20px 16px; }
  .is-embedded .settings-footer { grid-column: 1; grid-row: 4; padding: 10px 16px; }
  .runtime-grid, .form-row-2 { grid-template-columns: 1fr; }
  .overview-heading { gap: 16px; }
  .avatar-preview { grid-template-columns: 1fr; }
}

@media (max-width: 520px) {
  .console-brand > div > span, .connection-pill { display: none; }
  .runtime-grid { grid-template-columns: 1fr; }
  .footer-right { width: 100%; }
  .footer-right .btn { flex: 1; }
  .footer-left:empty { display: none; }
}
</style>
