package com.ghostinthedroid.portal

import android.graphics.Rect
import android.os.Build
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import io.mockk.every
import io.mockk.mockk
import io.mockk.spyk
import io.mockk.verify
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], manifest = Config.NONE)
class GhostAccessibilitySnapshotTest {
    private fun node(id: String, children: () -> List<AccessibilityNodeInfo> = { emptyList() }, size: Int = 50): AccessibilityNodeInfo {
        val node = mockk<AccessibilityNodeInfo>(relaxed = true)
        every { node.viewIdResourceName } returns id
        every { node.className } returns "android.view.View"
        every { node.windowId } returns 1
        every { node.childCount } answers { children().size }
        every { node.getChild(any()) } answers { children().getOrNull(firstArg()) }
        every { node.refresh() } returns true
        every { node.getBoundsInScreen(any()) } answers { firstArg<Rect>().set(0, 0, size, size) }
        return node
    }

    private fun service(root: AccessibilityNodeInfo?): GhostAccessibilityService {
        val service = spyk(GhostAccessibilityService())
        every { service.rootInActiveWindow } returns root
        every { service.windows } returns mutableListOf()
        if (Build.VERSION.SDK_INT >= 33) every { service.clearCache() } returns true
        return service
    }

    @Test
    fun selectedPieceTargetsAppearAndDisappearWithoutCachedChildren() {
        var actual = emptyList<AccessibilityNodeInfo>()
        var cached = emptyList<AccessibilityNodeInfo>()
        val root = node("board", { cached })
        val service = service(root)
        every { service.clearCache() } answers { cached = actual; true }
        assertFalse(service.getA11yTree()!!.toString().contains("legal-e4"))
        actual = listOf(node("legal-e4"))
        assertTrue(service.getA11yTree()!!.toString().contains("legal-e4"))
        actual = emptyList()
        assertFalse(service.getA11yTree()!!.toString().contains("legal-e4"))
        verify(exactly = 3) { service.clearCache() }
    }

    @Test
    @Config(sdk = [32])
    fun olderAndroidRefreshesVirtualDescendantsBeforeEnumeratingChildren() {
        val target = node("legal-e4")
        var children = emptyList<AccessibilityNodeInfo>()
        val board = node("board", { children })
        val root = node("root", { listOf(board) })
        every { board.refresh() } answers { children = listOf(target); true }
        assertTrue(service(root).getA11yTree()!!.toString().contains("legal-e4"))
        verify { root.refresh(); board.refresh(); target.refresh() }
    }

    @Test
    fun failedCacheClearFallsBackToRefreshingNodes() {
        var children = emptyList<AccessibilityNodeInfo>()
        val root = node("board", { children })
        val service = service(root)
        every { service.clearCache() } returns false
        every { root.refresh() } answers { children = listOf(node("legal-e4")); true }
        assertTrue(service.getA11yTree()!!.toString().contains("legal-e4"))
    }

    @Test
    fun inactiveApplicationPopupIsIncludedWithoutDuplicatingActiveRootOrPortalOverlay() {
        val root = node("board")
        val popup = node("legal-e4")
        val duplicate = mockk<AccessibilityWindowInfo>(relaxed = true)
        every { duplicate.id } returns 1
        every { duplicate.type } returns AccessibilityWindowInfo.TYPE_APPLICATION
        val window = mockk<AccessibilityWindowInfo>(relaxed = true)
        every { window.id } returns 2
        every { window.type } returns AccessibilityWindowInfo.TYPE_APPLICATION
        every { window.isActive } returns false
        every { window.root } returns popup
        val overlay = mockk<AccessibilityWindowInfo>(relaxed = true)
        every { overlay.id } returns 3
        every { overlay.type } returns AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY
        val service = service(root)
        every { service.windows } returns mutableListOf(duplicate, window, overlay)
        val tree = service.getA11yTree()!!
        assertEquals(2, tree.getJSONArray("children").length())
        assertTrue(tree.toString().contains("legal-e4"))
        verify(exactly = 0) { duplicate.root; overlay.root }
    }

    @Test
    fun fullTreeKeepsInvisibleUnlabelledZeroSizeTargets() {
        val target = node("legal-e4", size = 0)
        every { target.isVisibleToUser } returns false
        val tree = service(node("board", { listOf(target) })).getA11yTree()!!
        assertEquals("legal-e4", tree.getJSONArray("children").getJSONObject(0).getString("resourceId"))
        assertEquals(0, tree.getJSONArray("children").getJSONObject(0).getJSONObject("boundsInScreen").getInt("right"))
    }

    @Test
    fun flatElementsUseFreshSnapshotAndKeepIdOnlyTargets() {
        var actual = emptyList<AccessibilityNodeInfo>()
        var cached = emptyList<AccessibilityNodeInfo>()
        val service = service(node("board", { cached }))
        every { service.clearCache() } answers { cached = actual; true }
        val target = node("legal-e4")
        every { target.isEnabled } returns false
        every { target.isChecked } returns true
        every { target.isSelected } returns true
        every { target.isFocused } returns true
        actual = listOf(target)
        val elements = service.getElements()
        val cell = (0 until elements.length()).map { elements.getJSONObject(it) }
            .first { it.getString("resource_id") == "legal-e4" }
        assertFalse(cell.getBoolean("enabled"))
        for (key in listOf("checked", "selected", "focused")) assertTrue(cell.getBoolean(key))
        actual = emptyList()
        assertFalse(service.getElements().toString().contains("legal-e4"))
    }

    @Test
    fun applicationWindowIsAvailableDuringMissingActiveRootTransition() {
        val window = mockk<AccessibilityWindowInfo>(relaxed = true)
        every { window.id } returns 2
        every { window.type } returns AccessibilityWindowInfo.TYPE_APPLICATION
        every { window.root } returns node("legal-e4")
        val service = service(null)
        every { service.windows } returns mutableListOf(window)
        assertTrue(service.getA11yTree()!!.toString().contains("legal-e4"))
    }

    @Test
    fun unavailableWindowEnumerationKeepsActiveRoot() {
        val service = service(node("board"))
        every { service.windows } throws IllegalStateException("window changed")
        assertTrue(service.getA11yTree()!!.toString().contains("board"))
    }

    @Test
    @Config(sdk = [32])
    fun removedNodesAreNotReturnedWhenRefreshFails() {
        val target = node("stale-target")
        every { target.refresh() } returns false
        val tree = service(node("board", { listOf(target) })).getA11yTree()!!
        assertFalse(tree.toString().contains("stale-target"))
        verify { target.recycle() }
    }
}
