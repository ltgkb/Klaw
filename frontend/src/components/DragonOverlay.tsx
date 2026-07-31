import { useEffect, useRef } from "react"

export function DragonOverlay() {
  const frameRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    let animationFrame = 0
    let pointer = { x: window.innerWidth / 2, y: window.innerHeight / 2 }

    const sendPointer = () => {
      animationFrame = 0
      frameRef.current?.contentWindow?.postMessage(
        { type: "kai-dragon-pointer", x: pointer.x, y: pointer.y },
        window.location.origin,
      )
    }

    const handlePointerMove = (event: PointerEvent) => {
      pointer = { x: event.clientX, y: event.clientY }
      if (!animationFrame) animationFrame = window.requestAnimationFrame(sendPointer)
    }

    window.addEventListener("pointermove", handlePointerMove, { passive: true })
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
    }
  }, [])

  return (
    <iframe
      ref={frameRef}
      title="KAI 龙形环境动效"
      src="/dragon-kinematics.html"
      className="kai-dragon-overlay"
      sandbox="allow-scripts allow-same-origin"
      aria-hidden="true"
      tabIndex={-1}
    />
  )
}
