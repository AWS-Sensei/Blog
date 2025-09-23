---
title: "Fake Methods and Dependencies without Dependency Injection"
date: 2021-05-06T00:00:00+02:00
draft: false
author: "Marcel"
description: "Fake Dependencies with an Interface and Dependency Injection is easy and the usual approach. But how can you fake without Dependency Injection or an Interface. I will show you two situations that came up in production code."

images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

## Mocking via virtual method

Fake Dependencies with an Interface and Dependency Injection is easy and the usual approach. But how can you fake without Dependency Injection or an Interface. I will show you two situations that came up in production code.

### Factory Method

The first situation is a small AWS Lambda function with an http call. We want to mock the .Net HttpClient and write a UnitTest for our Request method.

Here you can see a simple example:

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

The first thing we do is create a wrapper for the HttpClient.

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

The second step is that we use a factory method to create an instance of the new `HttpClientHandler` class. The important part here is that the method has to be virtual.

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

With this little refactoring we can start writing our Test. To take control over the `IHttpHandler` we create a `FakeRequestService` and override the factory method.

```csharp
internal class FakeRequestService : RequestService
{
    public IHttpHandler HttpHandler { get; set; }
    protected override IHttpHandler GetHttpHandler => HttpHandler;
}
```

We can initialize the `FakeRequestService` with our own `IHttpHandler`. Now we have the control over `IHttpHandler` and can check if our `SendPostRequest` method called the `PostAsync` method with the correct parameters.

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

### Avoid unnecessary complexity in test

The second use case was a big `Product` model.

We consumed from the legacy system an `ProductUpdated` event and made in our new `ProductService` the decision that we will only execute an update in the database if the product really changed.

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

For our use case we decided to customize the `Equals` method.

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

We wrote a lot of `ProductTests` for the `Equals` method.
When we startet to write `ProductServiceTests` we didn't want to duplicate the test data from the `ProductTests` to simulate the `true` and `false` behavior. Instead we decided to fake the `Equals` result.

You can see that the `Equals` method is again virtual.
That means we can create a `ProductFake` and take control over the `boolean`.

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

Now we can easily write the `ProductServiceTests` test and focus 100% an the real logic and avoid a lot of unnecessary test code.

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

You can learn more about this topic in the book [The Art of Unit Testing](https://www.artofunittesting.com/) from Roy Osherove.