package com.example.flume.interceptors;

import java.util.List;
import java.util.Map;

import org.apache.flume.Context;
import org.apache.flume.Event;
import org.apache.flume.interceptor.Interceptor;

import org.apache.log4j.Logger;

public class eventTweaker implements Interceptor {

  private static final Logger LOG = Logger.getLogger(eventTweaker.class);

  // private means that only Builder can build me.
  private eventTweaker() {}

  @Override
  public void initialize() {}

  @Override
  public Event intercept(Event event) {

    Map&lt;String, String&gt; headers = event.getHeaders();

    // example: add / remove headers
    if (headers.containsKey("lice")) {
      headers.put("shampoo", "antilice");
      headers.remove("lice");
    }

    // example: change body
    String body = new String(event.getBody());
    if (body.contains("injuries")) {
      try {
        event.setBody("cyborg".getBytes("UTF-8"));
      } catch (java.io.UnsupportedEncodingException e) {
        LOG.warn(e);
        // drop event completely
        return null;
      }
    }

    return event;
  }

  @Override
  public List&lt;Event&gt; intercept(List&lt;Event&gt; events) {
    for (Event event:events) {
      intercept(event);
    }
    return events;
  }

  @Override
  public void close() {}

  public static class Builder implements Interceptor.Builder {

    @Override
    public Interceptor build() {
      return new eventTweaker();
    }

    @Override
    public void configure(Context context) {}
  }
}