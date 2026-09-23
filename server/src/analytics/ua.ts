/** Lecture sommaire de l'agent utilisateur : robots, type d'appareil, navigateur, système. */

const BOT = /bot\b|bot\/|crawl|spider|slurp|mediapartners|headless|lighthouse|pagespeed|gtmetrix|preview|facebookexternalhit|embedly|whatsapp|telegram|discord|skype|curl\/|wget|python|axios|node-fetch|undici|go-http|okhttp|java\/|libwww|httpclient|phantom|selenium|puppeteer|playwright|scrapy|monitor|uptime/i;

export const isBot = (ua: string) => !ua || BOT.test(ua);

export type Device = 'desktop' | 'mobile' | 'tablet';

export function device(ua: string, width?: number): Device {
  if (/iPad|Tablet|PlayBook|Silk|Kindle|(Android(?!.*Mobile))/i.test(ua)) return 'tablet';
  if (/Mobi|iPhone|iPod|Android|Windows Phone/i.test(ua)) return 'mobile';
  // iPadOS se présente comme un Mac : la largeur d'écran tranche.
  if (/Macintosh/.test(ua) && width && width <= 1366 && width >= 744) return 'tablet';
  return 'desktop';
}

export function browser(ua: string): string {
  if (/Edg(e|A|iOS)?\//.test(ua)) return 'Edge';
  if (/OPR\/|Opera|OPT\//.test(ua)) return 'Opera';
  if (/YaBrowser/.test(ua)) return 'Yandex';
  if (/SamsungBrowser/.test(ua)) return 'Samsung Internet';
  if (/Vivaldi/.test(ua)) return 'Vivaldi';
  if (/Firefox|FxiOS/.test(ua)) return 'Firefox';
  if (/CriOS|Chrome|Chromium/.test(ua)) return 'Chrome';
  if (/Safari/.test(ua)) return 'Safari';
  return 'Autre';
}

export function os(ua: string): string {
  if (/Windows/.test(ua)) return 'Windows';
  if (/iPhone|iPad|iPod/.test(ua)) return 'iOS';
  if (/Mac OS X|Macintosh/.test(ua)) return 'macOS';
  if (/Android/.test(ua)) return 'Android';
  if (/CrOS/.test(ua)) return 'ChromeOS';
  if (/Linux/.test(ua)) return 'Linux';
  return 'Autre';
}
