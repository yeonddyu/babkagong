import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ChatView from './views/ChatView.vue'
import PlansView from './views/PlansView.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/plans', name: 'plans', component: PlansView },
    { path: '/plans/:id', name: 'plan', component: PlansView },
  ],
})

createApp(App).use(router).mount('#app')
