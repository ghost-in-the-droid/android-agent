/**
 * GhostAgent extension: H.264-over-WebSocket screen stream.
 *
 * Self-contained: owns its own listening socket (so it can read the WebSocket
 * upgrade request, which FBTCPSocket drops). Captures frames, hardware-encodes
 * them to H.264 with VideoToolbox, and sends each access unit (Annex-B, with
 * SPS/PPS prepended on keyframes) as one binary WebSocket message.
 *
 * Browser side decodes with WebCodecs VideoDecoder. Far less bandwidth than
 * MJPEG and a clean single byte stream that a fleet master can relay.
 */
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface FBH264StreamServer : NSObject

- (instancetype)initWithPort:(uint16_t)port;
- (BOOL)startWithError:(NSError **)error;
- (void)stop;

@end

NS_ASSUME_NONNULL_END
