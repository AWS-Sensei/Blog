---
title: "Fake-Methoden und Abhängigkeiten ohne Dependency Injection"
date: 2021-05-06T00:00:00+02:00
draft: false
author: "Marcel"
description: "Fakes von Abhängigkeiten mit einem Interface und Dependency Injection sind einfach und üblich. Aber wie kann man faken, ohne Dependency Injection oder ein Interface zu verwenden? Ich zeige dir zwei Situationen, die im Produktivcode aufgetreten sind."

images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

## Mocking über virtuelle Methoden

Fakes von Abhängigkeiten mit einem Interface und Dependency Injection sind einfach und üblich.  
Aber wie kann man faken, ohne Dependency Injection oder ein Interface zu verwenden?  
Ich zeige dir zwei Situationen, die im Produktivcode aufgetreten sind.

### Factory Method

Die erste Situation war eine kleine AWS Lambda-Funktion mit einem HTTP-Call.  
Wir wollen den .NET `HttpClient` mocken und einen Unit Test für unsere `Request`-Methode schreiben.

Hier ein einfaches Beispiel:

```csharp
public class RequestService
{
    public async Task SendPostRequest()
    {
        var url = new Uri("https://test-uri.com");

        var _client = new HttpClient();
        var response = await _client.PostAsync(url, null);
    }
}
```

Der erste Schritt ist, einen Wrapper für den `HttpClient` zu erstellen:

```csharp
public interface IHttpHandler
{
    Task<HttpResponseMessage> PostAsync(Uri url, HttpContent content);
}
```

```csharp
public class HttpClientHandler : IHttpHandler
{
    private readonly HttpClient _client = new HttpClient();

    public async Task<HttpResponseMessage> PostAsync(Uri url,
    HttpContent content)
    {
        return await _client.PostAsync(url, content);
    }
}
```

Im zweiten Schritt nutzen wir eine Factory-Methode, um eine Instanz der neuen `HttpClientHandler`-Klasse zu erstellen.  
Wichtig ist hier, dass die Methode `virtual` sein muss:

```csharp
public class RequestService
{
    public async Task SendPostRequest()
    {
        var url = new Uri("https://test-uri.com");

        var httpHandler = GetHttpHandler();
        var response = await httpHandler.PostAsync(url, null);
    }

    protected virtual IHttpHandler GetHttpHandler
        => new HttpClientHandler();
}
```

Mit diesem kleinen Refactoring können wir Tests schreiben.  
Um die Kontrolle über den `IHttpHandler` zu übernehmen, erstellen wir einen `FakeRequestService` und überschreiben die Factory-Methode:

```csharp
internal class FakeRequestService : RequestService
{
    public IHttpHandler HttpHandler { get; set; }
    protected override IHttpHandler GetHttpHandler => HttpHandler;
}
```

Nun können wir den `FakeRequestService` mit unserem eigenen `IHttpHandler` initialisieren.  
Damit haben wir die Kontrolle über `IHttpHandler` und können prüfen, ob unsere `SendPostRequest`-Methode den Aufruf `PostAsync` mit den richtigen Parametern gemacht hat:

```csharp
public async Task PostRequestTest()
{
    var httpHandler = A.Fake<IHttpHandler>();
    var sut = new FakeRequestService { HttpHandler = httpHandler };

    await sut.SendPostRequest();

    var expectedUrl = new Uri("https://test-uri.com");
    A.CallTo(() => httpHandler.PostAsync(expectedUrl, null))
        .MustHaveHappenedOnceExactly();
}
```

### Unnötige Komplexität im Test vermeiden

Das zweite Beispiel war ein großes `Product`-Modell.  

Wir haben ein `ProductUpdated`-Event aus einem Legacy-System konsumiert und entschieden, im neuen `ProductService` nur dann ein Update in der Datenbank auszuführen, wenn sich das Produkt wirklich geändert hat.

```csharp
public class ProductService
{
    public bool CompareAndUpdate(Product product)
    {
        //get Product from database
        var existingProdcut = new Product();

        if (product.Equals(existingProdcut))
        {
            //do Nothing
            return false;
        }

        //update product
        return true;
    }
}
```

Für diesen Use Case haben wir die `Equals`-Methode angepasst:

```csharp
public class Product
{
    public virtual bool Equals(Product other)
    {
        return other != null;
        //&& do magic stuff

    }
}
```

Wir haben viele `ProductTests` für die `Equals`-Methode geschrieben.  
Als wir anfingen, `ProductServiceTests` zu schreiben, wollten wir die Testdaten aus den `ProductTests` nicht duplizieren, um das `true`- und `false`-Verhalten zu simulieren.  
Stattdessen haben wir beschlossen, das `Equals`-Ergebnis zu faken.

Da die `Equals`-Methode `virtual` ist, können wir ein `ProductFake` erstellen und die Kontrolle über den Rückgabewert übernehmen:

```csharp
public class ProductFake : Product
{
    public bool EqualState { get; set; }

    public override bool Equals(Product other)
    {
        return EqualState;
    }
}
```

Nun können wir die Tests für `ProductService` einfach schreiben, uns zu 100 % auf die eigentliche Logik konzentrieren und unnötigen Testcode vermeiden:

```csharp
public class ProductServiceTests
{
    public void ProductShouldBeUpdates()
    {
        var product = new ProductFake() { EqualState = false };

        var sut = new ServiceUnderTest();

        var result = sut.CompareAndUpdateIfNecessary(product);

        result.Should().BeTrue();
    }
}
```

Mehr über dieses Thema findest du im Buch [The Art of Unit Testing](https://www.artofunittesting.com/) von Roy Osherove.
