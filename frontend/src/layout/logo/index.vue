<template>
  <div class="layout-logo" v-if="setShowLogo" @click="onThemeConfigChange">
    <img :src="logos.mini" alt="" class="layout-logo-medium-img"/>
    <span class="layout-logo-title">{{ brand.name }}</span>
  </div>
  <div class="layout-logo-size" v-else @click="onThemeConfigChange">
    <img :src="logos.mini" :alt="brand.name" class="layout-logo-size-img"/>
  </div>
</template>

<script setup lang="ts" name="layoutLogo">
import {computed} from 'vue';
import {storeToRefs} from "/@/stores";
import {useThemeConfig} from '/@/stores/themeConfig';
import { logos } from '/@/config/assets';
import { brand } from '/@/config/brand';

// 定义变量内容
const storesThemeConfig = useThemeConfig();
const {themeConfig} = storeToRefs(storesThemeConfig);

// 设置 logo 的显示。classic 经典布局默认显示 logo
const setShowLogo = computed(() => {
  let {isCollapse, layout} = themeConfig.value;
  return !isCollapse || layout === 'classic' || document.body.clientWidth < 1000;
});
// logo 点击实现菜单展开/收起
const onThemeConfigChange = () => {
  if (themeConfig.value.layout === 'transverse') return false;
  themeConfig.value.isCollapse = !themeConfig.value.isCollapse;
};
</script>

<style scoped lang="scss">
.layout-logo {
  width: 220px;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 11px;
  padding: 0 17px;
  color: inherit;
  cursor: pointer;

  &-medium-img {
    width: 32px;
    height: 32px;
    object-fit: contain;
  }

  &-title {
    font-size: 17px;
    font-weight: 750;
    white-space: nowrap;
    letter-spacing: -0.02em;
    color: var(--next-bg-topBarColor);
  }
}

.layout-aside .layout-logo-title {
  color: var(--next-bg-menuBarColor);
}

.layout-logo-size {
  width: 100%;
  height: 50px;
  display: flex;
  cursor: pointer;
  animation: logoAnimation 0.3s ease-in-out;

  &-img {
    max-width: 32px;
    max-height: 32px;
    margin: auto;
    object-fit: contain;
  }

  &:hover {
    img {
      animation: logoAnimation 0.3s ease-in-out;
    }
  }
}
</style>
