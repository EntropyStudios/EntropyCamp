// Temporary Scriptable installer. Paste this once into a new Scriptable script.
const alert = new Alert();
alert.title = "安装微光提醒小组件";
alert.message = "输入Tailscale Funnel上的脚本下载地址。";
alert.addTextField("https://设备名.tailnet.ts.net/lumen/LumenToday.js", "");
alert.addAction("下载并安装");
alert.addCancelAction("取消");
if (await alert.present() < 0) Script.complete();

const sourceURL = alert.textFieldValue(0).trim();
if (!sourceURL.startsWith("https://") || !sourceURL.endsWith("/LumenToday.js")) {
  throw new Error("请输入以 /LumenToday.js 结尾的HTTPS地址");
}
const code = await new Request(sourceURL).loadString();
const currentPath = module.filename;
let manager = FileManager.local();
try {
  const cloud = FileManager.iCloud();
  if (currentPath.startsWith(cloud.documentsDirectory())) manager = cloud;
} catch {}
const folder = currentPath.slice(0, currentPath.lastIndexOf("/"));
manager.writeString(manager.joinPath(folder, "LumenToday.js"), code);

const done = new Alert();
done.title = "安装完成";
done.message = "返回脚本列表并运行 LumenToday 完成接口与令牌配置。若暂时没出现，请完全退出Scriptable后重新打开。";
done.addAction("完成");
await done.present();
Script.complete();
