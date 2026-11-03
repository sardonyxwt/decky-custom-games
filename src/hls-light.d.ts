// The light build of hls.js (no subtitles/DRM) has the same API as the full one.
declare module "hls.js/dist/hls.light.mjs" {
  import Hls from "hls.js";
  export default Hls;
}
