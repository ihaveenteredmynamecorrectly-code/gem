package dev.allhands.gemini_chat;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * Wraps the live Gemini Chat web app (GitHub Pages). The Gemini API key is
 * embedded AES-GCM encrypted (ciphertext + key live in the APK) and injected
 * into the page's localStorage on load, so the app works out-of-the-box with
 * no key entry. The key is never stored in plaintext in the APK or the repo.
 */
public class MainActivity extends Activity {

    private static final String WEB_URL = "https://ihaveenteredmynamecorrectly-code.github.io/gem/";

    // 256-bit AES key (obfuscation — ships in the APK; real secrecy is
    // impossible for client-side embedding, but the API key is not plaintext).
    private static final String KEY_HEX =
        "5f3a9c2e1b4d7e8a6c0f2a4b6d8e0f2a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d";

    // AES-GCM(128) ciphertext (IV prepended), base64. Decrypts to the Gemini key.
    private static final String CIPHER_B64 =
        "6CjKRm5MWh1qlXZJcFXlS/Z/y0hSWNhf84frvkOGf8SLJZdY4uhEGlu2ggcAhwCDXUhIg2NGnxd64SgesOxLy3qy57rpB92kmFCpuxtdn8Jb";

    private WebView web;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle s) {
        super.onCreate(s);
        web = new WebView(this);
        setContentView(web);

        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);   // localStorage
        web.getSettings().setDatabaseEnabled(true);
        web.getSettings().setUseWideViewPort(true);
        web.getSettings().setLoadWithOverviewMode(true);
        // Allow the WebView to retain a back-forward history so in-app navigation works.
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                return false;
            }
        });

        String apiKey = decrypt();
        if (apiKey == null) {
            web.loadDataWithBaseURL(null,
                "<h3 style='font:16px sans-serif;color:#f85149'>Failed to initialise. " +
                "Please reinstall the app.</h3>", "text/html", "utf-8", null);
            return;
        }

        final String key = apiKey;
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView v, String url) {
                // Inject the decrypted key into the page's localStorage so the
                // BYOK web app finds it pre-set. Then prime the UI state.
                String js = "(function(){" +
                    "try{localStorage.setItem('gemini_api_key', " + jsString(key) + ");}catch(e){}" +
                    "})();";
                v.evaluateJavascript(js, null);
                // Trigger the app's key-state refresh if present (defensive: no-op if absent).
                v.evaluateJavascript(
                    "(function(){try{if(typeof refreshKeyState==='function')refreshKeyState();" +
                    "else window.dispatchEvent(new Event('storage'));}catch(e){}})();", null);
            }
        });

        web.loadUrl(WEB_URL);
    }

    private String decrypt() {
        try {
            byte[] all = Base64.getDecoder().decode(CIPHER_B64);
            byte[] iv = new byte[12];
            byte[] ct = new byte[all.length - 12];
            System.arraycopy(all, 0, iv, 0, 12);
            System.arraycopy(all, 12, ct, 0, ct.length);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(hexToBytes(KEY_HEX), "AES"),
                   new GCMParameterSpec(128, iv));
            return new String(c.doFinal(ct), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }

    /** Minimal safe JS string literal encoder. */
    private static String jsString(String s) {
        StringBuilder b = new StringBuilder("'");
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            switch (ch) {
                case '\\': b.append("\\\\"); break;
                case '\'': b.append("\\'"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                default: b.append(ch);
            }
        }
        return b.append('\'').toString();
    }

    static byte[] hexToBytes(String h) {
        byte[] b = new byte[h.length() / 2];
        for (int i = 0; i < b.length; i++)
            b[i] = (byte) Integer.parseInt(h.substring(i * 2, i * 2 + 2), 16);
        return b;
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
