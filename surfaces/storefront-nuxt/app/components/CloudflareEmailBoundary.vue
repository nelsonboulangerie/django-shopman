<script lang="ts">
import { createCommentVNode, defineComponent, Fragment, h } from 'vue'

export default defineComponent({
  name: 'CloudflareEmailBoundary',
  props: {
    protect: {
      type: Boolean,
      default: false
    }
  },
  setup (props, { slots }) {
    return () => h(Fragment, null, props.protect
      ? [
          // Cloudflare's documented per-address opt-out. The edge consumes
          // these markers, so only SSR responses that will cross Cloudflare
          // may emit them; hydration renders the original text without them.
          createCommentVNode('email_off'),
          ...(slots.default?.() || []),
          createCommentVNode('/email_off')
        ]
      : slots.default?.())
  }
})
</script>
