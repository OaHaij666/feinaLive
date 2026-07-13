import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Root from '@app-root'
import './assets/styles/main.css'

const target = import.meta.env.VITE_APP_TARGET === 'console' ? 'console' : 'live'
document.documentElement.dataset.app = target
document.title = target === 'console' ? 'Feina Live Console' : 'Feina Live'

const app = createApp(Root)
app.use(createPinia())
app.mount('#app')
