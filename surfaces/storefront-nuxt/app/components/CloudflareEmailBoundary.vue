<script lang="ts">
import { createCommentVNode, defineComponent } from 'vue'

export default defineComponent({
  name: 'CloudflareEmailBoundary',
  setup (_props, { slots }) {
    // Cloudflare's documented per-address opt-out. Runtime comment VNodes are
    // deliberate: production template compilation removes source comments.
    // Keeping these nodes in both SSR and hydration prevents Cloudflare from
    // replacing plain text with an injected <a> before Vue starts.
    return () => [
      createCommentVNode('email_off'),
      slots.default?.(),
      createCommentVNode('/email_off')
    ]
  }
})
</script>
