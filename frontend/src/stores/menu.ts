import {defineStore} from 'pinia';
import {Session} from '/@/utils/storage';
import {useUserApi} from "/@/api/v1/system/user";
import {menuSchemaVersion, hasLegacyWeb3, validNavigationCache} from '/@/utils/menuCache';
const validMenuCache = () => validNavigationCache(Session.get('menuData'), Session.get('menuSchemaVersion'));

/**
 * 用户信息
 * @methods 设置菜单信息
 */
export const useMenuInfo = defineStore('useMenuInfo', {
	state: (): MenuDataState => ({
		menuData: [],
	}),
	actions: {

		async setUserInfos() {
			if (validMenuCache()) {
				this.menuData = Session.get('menuData');
			} else {
				this.menuData = await this.getMenuData();
			}
		},

		async getMenuData() {
			let data
			if (validMenuCache()) {
				data = Session.get('menuData');
			} else {
				try {
					let res = await useUserApi().getMenuByToken()
					this.menuData = data = res.data
					Session.set("menuData", this.menuData)
					// Refresh only navigation, preserving the original login and other session state.
					if (!hasLegacyWeb3(data)) Session.set('menuSchemaVersion', menuSchemaVersion);
				} catch (error) {
					console.error('获取菜单数据失败:', error);
					// 如果获取失败，返回空数组而不是undefined
					this.menuData = data = [];
				}
			}
			return data
		},

		getMenuList() {
			if (Session.get('menuData')) {
				return Session.get('menuData');
			}
		}
	},
});
