using NzbDrone.Core.Plugins;

namespace LMBridgePlugin
{
    public class LMBridgePlugin : Plugin
    {
        public override string Name => "LM Bridge API";
        public override string Owner => PluginInfo.Author;
        public override string GithubUrl => "https://github.com/HVR88/LM-Bridge";
    }
}
