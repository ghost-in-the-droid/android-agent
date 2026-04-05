import { ref } from 'vue'

const loaded = ref(false)
const loading = ref(false)

/**
 * Load mermaid.js from CDN and initialize.
 * Call renderMermaid() after injecting markdown HTML to convert
 * ```mermaid code blocks into SVG diagrams.
 */
export async function loadMermaid(): Promise<void> {
  if (loaded.value) return
  if (loading.value) {
    // Wait for existing load
    await new Promise<void>(resolve => {
      const check = setInterval(() => {
        if (loaded.value) { clearInterval(check); resolve() }
      }, 100)
    })
    return
  }
  loading.value = true
  const w = window as any
  if (w.mermaid) { loaded.value = true; loading.value = false; return }

  const script = document.createElement('script')
  script.src = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js'
  await new Promise<void>((resolve, reject) => {
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load mermaid'))
    document.head.appendChild(script)
  })

  w.mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
      primaryColor: '#6366f1',
      primaryTextColor: '#e2e8f0',
      primaryBorderColor: '#4338ca',
      lineColor: '#475569',
      secondaryColor: '#1e293b',
      tertiaryColor: '#0f172a',
      background: '#0b0f1a',
      mainBkg: '#1e293b',
      nodeBorder: '#4338ca',
      clusterBkg: '#111827',
      titleColor: '#e2e8f0',
      edgeLabelBackground: '#1e293b',
    },
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    fontSize: 13,
  })

  loaded.value = true
  loading.value = false
}

/**
 * Render all mermaid blocks within a container element.
 * Call this after setting innerHTML with markdown-rendered HTML.
 * Looks for both <pre class="mermaid"> and <code class="language-mermaid"> blocks.
 */
export async function renderMermaid(container?: HTMLElement): Promise<void> {
  await loadMermaid()
  const w = window as any
  if (!w.mermaid) return

  const root = container || document.body

  // Convert <pre><code class="language-mermaid">...</code></pre> to <pre class="mermaid">...</pre>
  root.querySelectorAll('code.language-mermaid').forEach(code => {
    const pre = code.parentElement
    if (pre?.tagName === 'PRE') {
      pre.className = 'mermaid'
      pre.textContent = code.textContent
    }
  })

  // Render all mermaid blocks
  const blocks = root.querySelectorAll('.mermaid:not([data-processed])')
  if (!blocks.length) return

  try {
    await w.mermaid.run({ nodes: blocks })
  } catch {
    // mermaid.run can throw on invalid diagrams — fail silently
  }
}

export function useMermaid() {
  return { loadMermaid, renderMermaid, loaded }
}
