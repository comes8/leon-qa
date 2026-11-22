<template>
  <section class="login-brand">
    <div class="brand-heading">
      <img :src="logos.mini" alt="" width="40" height="40" />
      <span>{{ brand.name }}</span>
    </div>

    <div class="brand-orbit" aria-hidden="true">
      <span class="orbit-node"></span>
      <img class="orbit-mark" :src="logos.mini" alt="" width="148" height="148" />
    </div>

    <h1>{{ brand.subtitle }}</h1>
  </section>
</template>

<script setup lang="ts" name="LoginLeftView">
import { logos } from '/@/config/assets';
import { brand } from '/@/config/brand';
</script>

<style lang="scss" scoped>
.login-brand {
  position: relative;
  display: grid;
  grid-template-rows: auto 1fr auto;
  width: 55%;
  min-width: 0;
  padding: clamp(28px, 5vw, 76px);
  overflow: hidden;
  isolation: isolate;
  background:
    radial-gradient(ellipse at 52% 45%, #203e4b 0%, transparent 68%),
    #101d2c;
  color: #eef7f6;

  &::before {
    position: absolute;
    z-index: -1;
    inset: 0;
    background-image:
      linear-gradient(rgba(160, 221, 217, 0.10) 1px, transparent 1px),
      linear-gradient(90deg, rgba(160, 221, 217, 0.10) 1px, transparent 1px);
    background-size: 44px 44px;
    mask-image: radial-gradient(ellipse at center, #000, transparent 77%);
    content: '';
  }

  h1 {
    margin: 0;
    font-size: clamp(26px, 4vw, 56px);
    font-weight: 650;
    letter-spacing: -0.04em;
    line-height: 1.15;
  }
}

.brand-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 19px;
  font-weight: 700;
}

.brand-orbit {
  position: relative;
  display: grid;
  place-items: center;
  place-self: center;
  width: min(100%, 38vh, 360px);
  aspect-ratio: 1;
  border: 1px solid rgba(152, 201, 216, 0.24);
  border-radius: 50%;

  &::before {
    position: absolute;
    inset: 12%;
    border: 1px dashed rgba(152, 201, 216, 0.35);
    border-radius: inherit;
    content: '';
  }
}

.orbit-mark {
  width: 54%;
  height: auto;
  transform: rotate(-9deg);
  filter: drop-shadow(0 16px 28px rgba(0, 0, 0, 0.3));
}

.orbit-node {
  position: absolute;
  top: 14%;
  right: 13%;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #69e7b8;
  box-shadow: 0 0 16px rgba(105, 231, 184, 0.7);
}

@media (max-width: 850px) {
  .login-brand { display: none; }
}
</style>
