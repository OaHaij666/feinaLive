import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Root from './App.vue'
import './assets/styles/main.css'

document.documentElement.dataset.app = 'live'
document.title = 'Feina Live'

const app = createApp(Root)
app.use(createPinia())
app.mount('#app')
