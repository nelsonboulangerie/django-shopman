import { config } from "@vue/test-utils";

// Component tests run without the Nuxt runtime. Tabs stay real because the
// contract under test is precisely the Reka-backed keyboard and selection
// behavior shared by the eight operator apps.
import UiTabs from "../../../operator-kit/app/components/Ui/Tabs/Tabs.vue";
import UiTabsList from "../../../operator-kit/app/components/Ui/Tabs/List.vue";
import UiTabsTrigger from "../../../operator-kit/app/components/Ui/Tabs/Trigger.vue";

config.global.components = {
  ...config.global.components,
  UiTabs,
  UiTabsList,
  UiTabsTrigger,
};
