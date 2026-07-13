<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="settings-overlay" @click.self="close">
        <div :class="['settings-panel', { 'settings-panel-wide': ['memory', 'agent_params', 'monitor'].includes(activeTab) }]">
          <div class="settings-header">
            <h2>集中配置</h2>
            <button class="close-btn" @click="close">&times;</button>
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
            <div class="settings-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                :class="['tab-btn', { active: activeTab === tab.key }]"
                @click="activeTab = tab.key"
              >
                {{ tab.label }}
              </button>
            </div>

            <div :class="['settings-content', { 'settings-content-memory': activeTab === 'memory' }]">
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
                <div class="section-title">📦 通用模型</div>
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

                <div class="section-title">🎙 主播模型</div>
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
                <div class="section-title">🧠 向量模型 (Embedding)</div>
                <p class="section-desc">用于记忆语义检索，未配置时自动退化到纯关键词检索</p>
                <div class="form-group">
                  <label>提供商</label>
                  <select v-model="cfg.embedding.provider">
                    <option value="openai">OpenAI</option>
                    <option value="azure">Azure</option>
                    <option value="ollama">Ollama</option>
                    <option value="custom">自定义</option>
                  </select>
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
                <div class="section-title">TTS 语音合成</div>
                <div class="form-group">
                  <label>提供商</label>
                  <select v-model="cfg.tts.provider">
                    <option value="volcano">火山引擎</option>
                    <option value="edge">Edge TTS</option>
                  </select>
                </div>
                <div class="form-group" v-if="cfg.tts.provider === 'edge'">
                  <label>TTS 语音 <span class="hint">(仅 Edge 有效)</span></label>
                  <select v-model="cfg.tts.voice">
                    <option value="zh-CN-XiaoxiaoNeural">晓晓 (女声)</option>
                    <option value="zh-CN-YunxiNeural">云希 (男声)</option>
                    <option value="zh-CN-YunyangNeural">云扬 (男声)</option>
                    <option value="zh-CN-XiaoyiNeural">晓伊 (女声)</option>
                    <option value="zh-CN-YunjianNeural">云健 (男声)</option>
                    <option value="zh-CN-YunhaoNeural">云浩 (男声)</option>
                    <option value="zh-CN-YunxiaNeural">云夏 (女声)</option>
                  </select>
                </div>
                <div class="form-group" v-if="cfg.tts.provider === 'volcano'">
                  <label>朗诵人 (Speaker ID)</label>
                  <input type="text" v-model="cfg.volcano.speaker_id" placeholder="火山引擎 Speaker ID" />
                </div>
                <div class="form-row-2">
                  <div class="form-group">
                    <label>编码格式</label>
                    <select v-model="cfg.tts.encoding">
                      <option value="wav">WAV</option>
                      <option value="mp3">MP3</option>
                    </select>
                  </div>
                  <div class="form-group">
                    <label>语速 <span class="range-value">{{ cfg.tts.speed_ratio }}</span></label>
                    <input type="range" v-model.number="cfg.tts.speed_ratio" min="0.5" max="2.0" step="0.1" />
                  </div>
                </div>

                <div class="section-title">火山引擎凭证 <span v-if="cfg.tts.provider !== 'volcano'" class="hint">(未使用)</span></div>
                <div class="form-group" :class="{ dimmed: cfg.tts.provider !== 'volcano' }">
                  <label>App ID</label>
                  <input type="text" v-model="cfg.volcano.appid" />
                </div>
                <div class="form-group" :class="{ dimmed: cfg.tts.provider !== 'volcano' }">
                  <label>Access Token <span v-if="cfg.volcano.access_token.includes(MASKED)" class="hint">(已隐藏)</span></label>
                  <input :type="cfg.volcano.access_token.includes(MASKED) ? 'password' : 'text'" v-model="cfg.volcano.access_token" />
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
              <div v-if="activeTab === 'easyvtuber'" class="tab-content">
                <div class="form-group">
                  <label class="checkbox-label"><input type="checkbox" v-model="cfg.easyvtuber.enabled" /> 启用数字人</label>
                </div>
                <div class="form-group">
                  <label>角色</label>
                  <div class="input-row">
                    <select v-model="cfg.easyvtuber.character" class="flex-select">
                      <option v-for="char in characters" :key="char.name" :value="char.name">{{ char.name }}</option>
                    </select>
                    <button class="small-btn" @click="openImagesFolder">打开图片文件夹</button>
                  </div>
                </div>
                <div class="section-title">输入</div>
                <div class="form-group">
                  <label>输入类型</label>
                  <select v-model="cfg.easyvtuber.input.type">
                    <option value="debug">调试</option><option value="webcam">摄像头</option><option value="mouse">鼠标</option><option value="openseeface">OpenSeeFace</option><option value="hybrid">混合</option>
                  </select>
                </div>
                <div class="form-row-2">
                  <div class="form-group"><label>OSF 地址</label><input type="text" v-model="cfg.easyvtuber.input.osf_address" /></div>
                  <div class="form-group"><label>鼠标范围</label><input type="text" v-model="cfg.easyvtuber.input.mouse_range" /></div>
                </div>
                <div class="section-title">模型</div>
                <div class="form-row-2">
                  <div class="form-group"><label>版本</label><select v-model="cfg.easyvtuber.model.version"><option value="v2">v2</option><option value="v3">v3</option></select></div>
                  <div class="form-group"><label>精度</label><select v-model="cfg.easyvtuber.model.precision"><option value="full">full</option><option value="half">half</option></select></div>
                </div>
                <div class="form-row-2">
                  <label class="checkbox-label"><input type="checkbox" v-model="cfg.easyvtuber.model.separable" /> 可分离卷积</label>
                  <label class="checkbox-label"><input type="checkbox" v-model="cfg.easyvtuber.model.use_tensorrt" /> TensorRT</label>
                  <label class="checkbox-label"><input type="checkbox" v-model="cfg.easyvtuber.model.use_eyebrow" /> 眉毛追踪</label>
                </div>
                <div class="section-title">性能</div>
                <div class="form-row-2">
                  <div class="form-group"><label>帧率</label><select v-model.number="cfg.easyvtuber.performance.frame_rate"><option :value="20">20</option><option :value="30">30</option><option :value="60">60</option></select></div>
                  <div class="form-group"><label>插帧</label><select v-model="cfg.easyvtuber.performance.interpolation"><option value="x1">关</option><option value="x2">2x</option><option value="x4">4x</option></select></div>
                  <div class="form-group"><label>超分</label><select v-model="cfg.easyvtuber.performance.super_resolution"><option value="x1">关</option><option value="x2">2x</option><option value="x4">4x</option></select></div>
                </div>
                <div class="form-row-2">
                  <div class="form-group"><label>内存缓存</label><select v-model="cfg.easyvtuber.performance.ram_cache"><option value="1gb">1G</option><option value="2gb">2G</option><option value="4gb">4G</option></select></div>
                  <div class="form-group"><label>显存缓存</label><select v-model="cfg.easyvtuber.performance.vram_cache"><option value="1gb">1G</option><option value="2gb">2G</option><option value="4gb">4G</option></select></div>
                  <div class="form-group"><label class="checkbox-label"><input type="checkbox" v-model="cfg.easyvtuber.output.websocket.enabled" /> WS</label></div>
                </div>
                <div class="form-row-2">
                  <div class="form-group"><label>WS 主机</label><input type="text" v-model="cfg.easyvtuber.output.websocket.host" /></div>
                  <div class="form-group"><label>WS 端口</label><input type="number" v-model.number="cfg.easyvtuber.output.websocket.port" min="1000" max="65535" /></div>
                </div>
              </div>

              <!-- Tab: Agent 参数 -->
              <div v-if="activeTab === 'agent_params'" class="tab-content">
                <AgentSettingsPanel v-model="cfg.agent" />
              </div>

              <!-- Tab: 音乐 -->
              <div v-if="activeTab === 'music'" class="tab-content">
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

            <div v-if="activeTab !== 'memory'" class="settings-footer">
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
import MemoryDebugPanel from '@/components/memory/MemoryDebugPanel.vue'
import AgentSettingsPanel from '@/components/settings/agent/AgentSettingsPanel.vue'

interface Props { visible: boolean }
const props = defineProps<Props>()
const emit = defineEmits<{ close: []; saved: [] }>()

// ---- 依赖 ----
const musicStore = useMusicStore()
const { state: musicState } = storeToRefs(musicStore)

// ---- 连接状态（配置仅从后端获取，前端不缓存） ----
const connected = ref(false)
const connecting = ref(false)

// ---- Tabs ----
const tabs = [
  { key: 'host', label: 'AI主播' },
  { key: 'ai_models', label: 'AI模型' },
  { key: 'tts', label: '语音' },
  { key: 'messaging', label: '消息调度' },
  { key: 'easyvtuber', label: '数字人' },
  { key: 'agent_params', label: 'Agent 场景' },
  { key: 'music', label: '音乐' },
  { key: 'live', label: '直播' },
  { key: 'monitor', label: '直播状况' },
  { key: 'memory', label: '记忆' },
]
const activeTab = ref('host')
const characters = ref<{ name: string }[]>([])
const saveStatus = ref('')

function setLocalDirectories(event: Event) {
  cfg.music.local_directories = (event.target as HTMLTextAreaElement).value
    .split(/\r?\n/)
    .map(value => value.trim())
    .filter(Boolean)
}
const saveStatusText = ref('')
const vectorStatus = reactive({ available: false, vector_count: 0 })

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
    tts: { provider: 'volcano', voice: 'zh-CN-XiaoxiaoNeural', encoding: 'wav', speed_ratio: 1.0 },
    volcano: { appid: '', access_token: '', speaker_id: '' },
    agent: { enabled: false, scenario_id: 'slay_the_spire', mcp_url: 'http://127.0.0.1:8080', api_url: '', api_key: '', model: '', temperature: 0.4, max_tokens: 500, disable_thinking: true, poll_interval: 1.0, memory_threshold: 30, memory_idle_seconds: 120, memory_scan_interval_seconds: 30, memory_context_max_chars: 12000, min_step_interval: 3.0, step_jitter: 0.5, commentary_interval: 30.0, min_commentary_interval: 15.0, commentary_hold_timeout: 20.0, memory_eagerness: 3, queue_max_size: 20, host_history_maxlen: 50, action_history_maxlen: 30, scenario_config: { default_character: 'IRONCLAD' } },
    easyvtuber: { enabled: true, character: 'feina00', input: { type: 'debug', osf_address: '127.0.0.1:11573', mouse_range: '0,0,1920,1080' }, model: { version: 'v3', precision: 'half', separable: true, use_tensorrt: true, use_eyebrow: true }, performance: { frame_rate: 30, interpolation: 'x2', super_resolution: 'off', ram_cache: '2gb', vram_cache: '2gb' }, output: { websocket: { enabled: true, port: 8765, host: 'localhost' } } },
    ai: { max_history_per_session: 16, summary_interval: 10, summary_idle_seconds: 300.0, summary_scan_interval_seconds: 60.0, max_recent_messages: 16, poll_interval_seconds: 10.0 },
    messaging: { danmaku_starvation_seconds: 30.0, danmaku_flood_threshold: 5, danmaku_flood_window: 20.0, gift_starvation_seconds: 60.0, gift_flood_threshold: 3, gift_flood_window: 30.0, gift_value_highest: 10000, gift_value_high: 5000, gift_value_normal: 1000, gift_value_low: 100, user_cooldown_seconds: 3.0, default_ttl_seconds: 30.0, rate_limit_commentary: 4.0, rate_limit_danmaku: 3.0, rate_limit_gift: 10.0 },
    music: { default_provider: 'auto', min_duration_seconds: 60, max_duration_seconds: 480, queue_capacity: 5, per_user_limit: 2, allow_bare_bv: false, accept_score: 60, reject_score: -50, llm_min_confidence: 0.75, search_candidates: 5, ducking_factor: 0.2, ducking_enabled: true, local_directories: [] },
    storage: { sqlite_path: 'data/feinalive.db', chroma_path: 'data/chroma', chroma_collection: 'memory_atoms' },
    announcement: '',
    admin: { username: '', identities: { bilibili: '', douyin: '', test: 'internal' } },
    embedding: { provider: 'openai', model: '', api_url: '', api_key: '', dimensions: null, user_graph_enabled: true, game_graph_enabled: true },
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
  } catch (e) {
    console.error('连接后端失败:', e)
    connected.value = false
  } finally {
    connecting.value = false
  }
}

async function loadCharacters() {
  try {
    const res = await fetch('/config/easyvtuber/characters')
    const data = await res.json()
    characters.value = data.characters || []
  } catch { /* ignore */ }
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
    await fetch('/config/easyvtuber/open-images', { method: 'POST' })
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
    const res = await fetch('/test/admin/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command }) })
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
      fetch('/test/admin/state'),
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
  if (e.key === 'Escape' && props.visible) close()
}

watch(() => props.visible, (visible) => {
  if (visible) {
    loadConfig()
    loadCharacters()
    refreshStatus()
    refreshVectorStatus()
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  connectWebSocket()
  refreshStatus()
  refreshVectorStatus()
})

onUnmounted(() => {
  shouldReconnect = false
  if (wsReconnectTimer) clearTimeout(wsReconnectTimer)
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
</style>
