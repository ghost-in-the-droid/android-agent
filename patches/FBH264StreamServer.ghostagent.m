/**
 * GhostAgent extension: H.264-over-WebSocket screen stream.
 * Compiled via a textual #import at the bottom of FBMjpegServer.m, so the
 * FBH264StreamServer @interface comes from FBMjpegServer.h (already imported in
 * that TU). Do NOT import FBH264StreamServer.h here — it is not in the header map.
 */
#import <mach/mach_time.h>
// @import triggers Clang module auto-linking, so these frameworks link into the
// final app without a pbxproj link-phase change (same pattern as the MJPEG file).
@import CommonCrypto;
@import VideoToolbox;
@import CoreMedia;
@import CoreVideo;
@import ImageIO;
@import CoreGraphics;
@import UniformTypeIdentifiers;

#import "GCDAsyncSocket.h"
#import "FBConfiguration.h"
#import "FBLogger.h"
#import "FBScreenshot.h"
#import "XCUIScreen.h"

static const NSUInteger DEFAULT_FPS = 30;
static const NSTimeInterval H264_FRAME_TIMEOUT = 1.0;
static NSString *const WS_MAGIC = @"258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
static const char *H264_QUEUE_NAME = "GhostAgent H264 Stream Queue";
static const char *H264_SOCK_QUEUE_NAME = "GhostAgent H264 Socket Queue";
static const long TAG_HANDSHAKE = 1;
static const long TAG_KEEPALIVE = 2;

@interface FBH264StreamServer () <GCDAsyncSocketDelegate>
@property (nonatomic, readonly) dispatch_queue_t queue;
@property (nonatomic, strong) GCDAsyncSocket *listener;
@property (nonatomic, assign) uint16_t port;
@property (nonatomic, readonly) NSMutableArray<GCDAsyncSocket *> *pending;   // connected, pre-handshake
@property (nonatomic, readonly) NSMutableArray<GCDAsyncSocket *> *clients;   // handshaken, streaming
@property (nonatomic, assign) long long mainScreenID;
@property (nonatomic, assign) VTCompressionSessionRef session;
@property (nonatomic, assign) int32_t encW;
@property (nonatomic, assign) int32_t encH;
@property (atomic, assign) BOOL streaming;
@property (nonatomic, assign) BOOL needKeyframe;
@property (nonatomic, assign) NSUInteger frameCount;
@end

@implementation FBH264StreamServer

- (instancetype)initWithPort:(uint16_t)port
{
  if ((self = [super init])) {
    _port = port;
    _pending = [NSMutableArray array];
    _clients = [NSMutableArray array];
    _mainScreenID = [XCUIScreen.mainScreen displayID];
    _streaming = YES;
    _needKeyframe = YES;
    dispatch_queue_attr_t attr = dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INITIATED, 0);
    _queue = dispatch_queue_create(H264_QUEUE_NAME, attr);
  }
  return self;
}

- (BOOL)startWithError:(NSError **)error
{
  dispatch_queue_t sockQueue = dispatch_queue_create(H264_SOCK_QUEUE_NAME, DISPATCH_QUEUE_SERIAL);
  self.listener = [[GCDAsyncSocket alloc] initWithDelegate:self delegateQueue:sockQueue];
  if (![self.listener acceptOnPort:self.port error:error]) {
    [FBLogger logFmt:@"[GhostAgent] H264 stream server cannot listen on port %d", self.port];
    return NO;
  }
  __weak typeof(self) weakSelf = self;
  dispatch_async(self.queue, ^{ [weakSelf captureLoop]; });
  [FBLogger logFmt:@"[GhostAgent] H264 WebSocket stream server listening on port %d", self.port];
  return YES;
}

- (void)stop { [self stopStreaming]; }

#pragma mark - GCDAsyncSocketDelegate

- (void)socket:(GCDAsyncSocket *)sock didAcceptNewSocket:(GCDAsyncSocket *)newSocket
{
  @synchronized (self.pending) { [self.pending addObject:newSocket]; }
  // Read up to the end of the HTTP upgrade request headers.
  NSData *terminator = [@"\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding];
  [newSocket readDataToData:terminator withTimeout:5.0 tag:TAG_HANDSHAKE];
}

- (void)socket:(GCDAsyncSocket *)sock didReadData:(NSData *)data withTag:(long)tag
{
  if (tag == TAG_HANDSHAKE) {
    NSString *request = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"";
    [self handshakeClient:sock withRequest:request];
  }
  // TAG_KEEPALIVE reads are only to detect disconnects; ignore incoming frames.
}

- (void)socketDidDisconnect:(GCDAsyncSocket *)sock withError:(NSError *)err
{
  @synchronized (self.pending) { [self.pending removeObject:sock]; }
  @synchronized (self.clients) { [self.clients removeObject:sock]; }
}

- (void)handshakeClient:(GCDAsyncSocket *)client withRequest:(NSString *)request
{
  NSString *key = nil;
  for (NSString *line in [request componentsSeparatedByString:@"\r\n"]) {
    NSRange r = [line rangeOfString:@"Sec-WebSocket-Key:" options:NSCaseInsensitiveSearch];
    if (r.location != NSNotFound) {
      key = [[line substringFromIndex:r.location + r.length] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
      break;
    }
  }
  if (key.length == 0) {
    [client disconnect];
    return;
  }
  NSString *accept = [self wsAcceptForKey:key];
  NSString *resp = [NSString stringWithFormat:
      @"HTTP/1.1 101 Switching Protocols\r\n"
      @"Upgrade: websocket\r\nConnection: Upgrade\r\n"
      @"Sec-WebSocket-Accept: %@\r\n\r\n", accept];
  [client writeData:[resp dataUsingEncoding:NSUTF8StringEncoding] withTimeout:H264_FRAME_TIMEOUT tag:0];
  @synchronized (self.pending) { [self.pending removeObject:client]; }
  @synchronized (self.clients) { [self.clients addObject:client]; }
  self.needKeyframe = YES;   // force an IDR so the new client can start decoding
  // Keep a pending read so GCDAsyncSocket reports a disconnect promptly.
  [client readDataWithTimeout:-1 tag:TAG_KEEPALIVE];
  [FBLogger logFmt:@"[GhostAgent] H264 stream client connected: %@:%d", client.connectedHost, client.connectedPort];
}

- (NSString *)wsAcceptForKey:(NSString *)key
{
  NSString *concat = [key stringByAppendingString:WS_MAGIC];
  NSData *d = [concat dataUsingEncoding:NSUTF8StringEncoding];
  unsigned char digest[CC_SHA1_DIGEST_LENGTH];
  CC_SHA1(d.bytes, (CC_LONG)d.length, digest);
  return [[NSData dataWithBytes:digest length:CC_SHA1_DIGEST_LENGTH] base64EncodedStringWithOptions:(NSDataBase64EncodingOptions)0];
}

#pragma mark - WebSocket binary frame

- (void)sendBinary:(NSData *)payload toClient:(GCDAsyncSocket *)client
{
  NSMutableData *frame = [NSMutableData data];
  uint8_t b0 = 0x82;  // FIN=1, opcode=2 (binary)
  [frame appendBytes:&b0 length:1];
  NSUInteger len = payload.length;
  if (len < 126) {
    uint8_t b1 = (uint8_t)len;  // no mask bit (server frames are unmasked)
    [frame appendBytes:&b1 length:1];
  } else if (len <= 0xFFFF) {
    uint8_t b1 = 126; [frame appendBytes:&b1 length:1];
    uint8_t ext[2] = { (uint8_t)(len >> 8), (uint8_t)(len & 0xFF) };
    [frame appendBytes:ext length:2];
  } else {
    uint8_t b1 = 127; [frame appendBytes:&b1 length:1];
    uint8_t ext[8];
    for (int i = 0; i < 8; i++) { ext[i] = (uint8_t)((len >> (8 * (7 - i))) & 0xFF); }
    [frame appendBytes:ext length:8];
  }
  [frame appendData:payload];
  [client writeData:frame withTimeout:H264_FRAME_TIMEOUT tag:0];
}

- (void)broadcast:(NSData *)accessUnit
{
  @synchronized (self.clients) {
    for (GCDAsyncSocket *c in self.clients) { [self sendBinary:accessUnit toClient:c]; }
  }
}

#pragma mark - Capture + encode loop

- (NSUInteger)fps
{
  NSUInteger f = FBConfiguration.mjpegServerFramerate;   // reuse the same knob
  return (f == 0 || f > 60) ? DEFAULT_FPS : f;
}

- (void)captureLoop
{
  if (!self.streaming) { return; }
  uint64_t started = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
  uint64_t interval = (uint64_t)(1.0 / (double)[self fps] * NSEC_PER_SEC);

  BOOL hasClients;
  @synchronized (self.clients) { hasClients = self.clients.count > 0; }
  if (hasClients) { [self captureAndEncodeOnce]; }

  __weak typeof(self) weakSelf = self;
  uint64_t elapsed = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) - started;
  int64_t delta = (int64_t)interval - (int64_t)elapsed;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, MAX((int64_t)0, delta)), self.queue, ^{ [weakSelf captureLoop]; });
}

- (void)captureAndEncodeOnce
{
  NSError *err = nil;
  NSData *jpeg = [FBScreenshot takeInOriginalResolutionWithScreenID:self.mainScreenID
                                                 compressionQuality:0.9
                                                                uti:UTTypeJPEG
                                                            timeout:H264_FRAME_TIMEOUT
                                                              error:&err];
  if (jpeg == nil) { return; }
  CGImageSourceRef src = CGImageSourceCreateWithData((__bridge CFDataRef)jpeg, NULL);
  if (src == NULL) { return; }
  CGImageRef img = CGImageSourceCreateImageAtIndex(src, 0, NULL);
  CFRelease(src);
  if (img == NULL) { return; }

  // Encode at a SCALED resolution (reuses the mjpegScalingFactor knob, e.g. 50).
  // Full-res 1178x2556 H.264 decode + full-canvas draw bottlenecks the browser
  // to a few fps; half-res is ~4x less decode/draw work and bandwidth. The
  // CGImage is drawn scaled into the smaller pixel buffer by CGContextDrawImage.
  CGFloat scale = FBConfiguration.mjpegScalingFactor / 100.0;
  if (scale <= 0.0 || scale > 1.0) { scale = 0.5; }
  int32_t fullW = (int32_t)CGImageGetWidth(img);
  int32_t fullH = (int32_t)CGImageGetHeight(img);
  int32_t w = ((int32_t)(fullW * scale)) & ~1;   // keep even (H.264 requirement)
  int32_t h = ((int32_t)(fullH * scale)) & ~1;
  if (w < 2 || h < 2) { CGImageRelease(img); return; }
  if (![self ensureSessionForWidth:w height:h]) { CGImageRelease(img); return; }

  CVPixelBufferRef pb = [self pixelBufferFromImage:img width:w height:h];
  CGImageRelease(img);
  if (pb == NULL) { return; }

  VTEncodeInfoFlags flags;
  CMTime pts = CMTimeMake((int64_t)self.frameCount++, (int32_t)[self fps]);
  NSDictionary *frameProps = self.needKeyframe ? @{ (__bridge NSString *)kVTEncodeFrameOptionKey_ForceKeyFrame : @YES } : nil;
  self.needKeyframe = NO;
  VTCompressionSessionEncodeFrame(self.session, pb, pts, kCMTimeInvalid,
                                  (__bridge CFDictionaryRef)frameProps, NULL, &flags);
  CVPixelBufferRelease(pb);
}

- (BOOL)ensureSessionForWidth:(int32_t)w height:(int32_t)h
{
  if (self.session != NULL && self.encW == w && self.encH == h) { return YES; }
  if (self.session != NULL) {
    VTCompressionSessionInvalidate(self.session);
    CFRelease(self.session);
    self.session = NULL;
  }
  // Enable the low-latency H.264 encoder (WWDC21) — hardware, no frame reordering,
  // tuned for real-time streaming.
  NSDictionary *encSpec = @{
    (__bridge NSString *)kVTVideoEncoderSpecification_EnableLowLatencyRateControl : @YES,
  };
  VTCompressionSessionRef s = NULL;
  OSStatus st = VTCompressionSessionCreate(kCFAllocatorDefault, w, h, kCMVideoCodecType_H264,
                                           (__bridge CFDictionaryRef)encSpec, NULL, NULL,
                                           h264OutputCallback, (__bridge void *)self, &s);
  if (st != noErr || s == NULL) {
    [FBLogger logFmt:@"[GhostAgent] VTCompressionSessionCreate failed: %d", (int)st];
    return NO;
  }
  VTSessionSetProperty(s, kVTCompressionPropertyKey_RealTime, kCFBooleanTrue);
  VTSessionSetProperty(s, kVTCompressionPropertyKey_AllowFrameReordering, kCFBooleanFalse);
  VTSessionSetProperty(s, kVTCompressionPropertyKey_ProfileLevel, kVTProfileLevel_H264_Baseline_AutoLevel);
  // Cap the bitrate so keyframes don't spike over the tunnel (~6 Mbps).
  int32_t bitrate = 6 * 1000 * 1000;
  CFNumberRef brn = CFNumberCreate(NULL, kCFNumberSInt32Type, &bitrate);
  VTSessionSetProperty(s, kVTCompressionPropertyKey_AverageBitRate, brn);
  CFRelease(brn);
  int32_t kf = (int32_t)[self fps] * 2;   // keyframe every ~2s
  CFNumberRef kfn = CFNumberCreate(NULL, kCFNumberSInt32Type, &kf);
  VTSessionSetProperty(s, kVTCompressionPropertyKey_MaxKeyFrameInterval, kfn);
  CFRelease(kfn);
  VTCompressionSessionPrepareToEncodeFrames(s);
  self.session = s;
  self.encW = w; self.encH = h;
  self.needKeyframe = YES;
  return YES;
}

- (CVPixelBufferRef)pixelBufferFromImage:(CGImageRef)img width:(int32_t)w height:(int32_t)h
{
  NSDictionary *attrs = @{ (__bridge NSString *)kCVPixelBufferCGImageCompatibilityKey : @YES,
                           (__bridge NSString *)kCVPixelBufferCGBitmapContextCompatibilityKey : @YES };
  CVPixelBufferRef pb = NULL;
  CVReturn r = CVPixelBufferCreate(kCFAllocatorDefault, w, h, kCVPixelFormatType_32BGRA,
                                   (__bridge CFDictionaryRef)attrs, &pb);
  if (r != kCVReturnSuccess || pb == NULL) { return NULL; }
  CVPixelBufferLockBaseAddress(pb, (CVPixelBufferLockFlags)0);
  void *base = CVPixelBufferGetBaseAddress(pb);
  CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
  CGContextRef ctx = CGBitmapContextCreate(base, w, h, 8, CVPixelBufferGetBytesPerRow(pb), cs,
                                           (CGBitmapInfo)(kCGImageAlphaNoneSkipFirst | kCGBitmapByteOrder32Little));
  CGColorSpaceRelease(cs);
  if (ctx == NULL) { CVPixelBufferUnlockBaseAddress(pb, (CVPixelBufferLockFlags)0); CVPixelBufferRelease(pb); return NULL; }
  CGContextDrawImage(ctx, CGRectMake(0, 0, w, h), img);
  CGContextRelease(ctx);
  CVPixelBufferUnlockBaseAddress(pb, (CVPixelBufferLockFlags)0);
  return pb;
}

#pragma mark - Encoder output → Annex-B → WebSocket

static const uint8_t kStartCode[4] = { 0x00, 0x00, 0x00, 0x01 };

static void h264OutputCallback(void *outputCallbackRefCon, void *sourceFrameRefCon,
                               OSStatus status, VTEncodeInfoFlags infoFlags,
                               CMSampleBufferRef sampleBuffer)
{
  if (status != noErr || sampleBuffer == NULL || !CMSampleBufferDataIsReady(sampleBuffer)) { return; }
  FBH264StreamServer *self = (__bridge FBH264StreamServer *)outputCallbackRefCon;

  BOOL keyframe = YES;
  CFArrayRef attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, false);
  if (attachments != NULL && CFArrayGetCount(attachments) > 0) {
    CFDictionaryRef d = CFArrayGetValueAtIndex(attachments, 0);
    CFBooleanRef notSync = NULL;
    if (CFDictionaryGetValueIfPresent(d, kCMSampleAttachmentKey_NotSync, (const void **)&notSync)) {
      keyframe = !CFBooleanGetValue(notSync);
    }
  }

  NSMutableData *au = [NSMutableData data];

  if (keyframe) {
    CMFormatDescriptionRef fmt = CMSampleBufferGetFormatDescription(sampleBuffer);
    size_t count = 0;
    if (CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmt, 0, NULL, NULL, &count, NULL) == noErr) {
      for (size_t i = 0; i < count; i++) {
        const uint8_t *ps = NULL; size_t psLen = 0;
        if (CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmt, i, &ps, &psLen, NULL, NULL) == noErr) {
          [au appendBytes:kStartCode length:4];
          [au appendBytes:ps length:psLen];
        }
      }
    }
  }

  CMBlockBufferRef bb = CMSampleBufferGetDataBuffer(sampleBuffer);
  size_t totalLen = 0; char *dataPtr = NULL;
  if (CMBlockBufferGetDataPointer(bb, 0, NULL, &totalLen, &dataPtr) == noErr) {
    size_t offset = 0;
    while (offset + 4 <= totalLen) {
      uint32_t naluLen = 0;
      memcpy(&naluLen, dataPtr + offset, 4);
      naluLen = CFSwapInt32BigToHost(naluLen);   // AVCC is big-endian length-prefixed
      offset += 4;
      if (offset + naluLen > totalLen) { break; }
      [au appendBytes:kStartCode length:4];
      [au appendBytes:(dataPtr + offset) length:naluLen];
      offset += naluLen;
    }
  }

  if (au.length > 0) {
    dispatch_async(self.queue, ^{ [self broadcast:au]; });
  }
}

#pragma mark - Lifecycle

- (void)stopStreaming
{
  self.streaming = NO;
  if (self.session != NULL) {
    VTCompressionSessionInvalidate(self.session);
    CFRelease(self.session);
    self.session = NULL;
  }
  @synchronized (self.clients) {
    for (GCDAsyncSocket *c in self.clients.copy) { [c disconnect]; }
    [self.clients removeAllObjects];
  }
}

- (void)dealloc { [self stopStreaming]; }

@end
