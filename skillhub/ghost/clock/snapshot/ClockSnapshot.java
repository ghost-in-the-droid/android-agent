// Read-only, app-scoped accessibility snapshot for animated Clock screens.
// No input injection, private-file reads, settings changes or installed service.
package ghost.clock;
import android.graphics.Rect;
import android.view.accessibility.AccessibilityNodeInfo;
import android.util.Xml;
import org.xmlpull.v1.XmlSerializer;
import java.io.StringWriter;
public class ClockSnapshot extends com.android.uiautomator.testrunner.UiAutomatorTestCase {
 private static String str(CharSequence s) { return s == null ? "" : s.toString(); }
 private static int count = 0;
 private static void node(XmlSerializer x, AccessibilityNodeInfo n) throws Exception {
  if (n == null || !n.isVisibleToUser()) return;
  if (++count > 2000) throw new IllegalStateException("Too many nodes");
  Rect b = new Rect(); n.getBoundsInScreen(b);
  x.startTag(null,"node");
  x.attribute(null,"package",str(n.getPackageName()));
  x.attribute(null,"resource-id",str(n.getViewIdResourceName()));
  x.attribute(null,"text",str(n.getText()));
  x.attribute(null,"content-desc",str(n.getContentDescription()));
  x.attribute(null,"bounds",b.toShortString());
  x.attribute(null,"checked",String.valueOf(n.isChecked()));
  for(int i=0;i<n.getChildCount();i++) { AccessibilityNodeInfo c=n.getChild(i); node(x,c); if(c!=null)c.recycle(); }
  x.endTag(null,"node");
 }
 public void testSnapshot() throws Exception {
  java.lang.reflect.Method getter = com.android.uiautomator.core.UiDevice.class.getDeclaredMethod("getAutomatorBridge"); getter.setAccessible(true);
  Object bridge=getter.invoke(getUiDevice());
  java.lang.reflect.Method rootGetter=Class.forName("com.android.uiautomator.core.UiAutomatorBridge").getDeclaredMethod("getRootInActiveWindow");rootGetter.setAccessible(true);
  AccessibilityNodeInfo root=null;
  for(int i=0;i<10 && root==null;i++){Thread.sleep(100);root=(AccessibilityNodeInfo)rootGetter.invoke(bridge);}
  if(root==null || !("com.google.android.deskclock".contentEquals(root.getPackageName()) || "com.sec.android.app.clockpackage".contentEquals(root.getPackageName()))) throw new IllegalStateException("Clock not the active window");
  StringWriter out=new StringWriter();XmlSerializer x=Xml.newSerializer();x.setOutput(out);x.startDocument("UTF-8",true);x.startTag(null,"hierarchy");node(x,root);x.endTag(null,"hierarchy");x.endDocument();System.out.println("CLOCK_XML:"+out.toString());root.recycle();
 }
}
