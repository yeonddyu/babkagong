<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark">밥</span>
        <span class="brand-text">밥카공<small>밥 먹고 카공까지, 강남·역삼</small></span>
      </RouterLink>
      <nav class="nav">
        <RouterLink to="/" class="nav-link" exact-active-class="active">추천 대화</RouterLink>
        <RouterLink to="/plans" class="nav-link" active-class="active">저장한 계획</RouterLink>
      </nav>
    </header>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
